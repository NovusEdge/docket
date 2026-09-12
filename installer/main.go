package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"

	"github.com/charmbracelet/x/term"
)

var version = "dev"

type harnessFlags []string

func (h *harnessFlags) String() string     { return fmt.Sprint([]string(*h)) }
func (h *harnessFlags) Set(s string) error { *h = append(*h, s); return nil }

func parseOptions(args []string, out io.Writer) (Options, error) {
	var opts Options
	var selected harnessFlags
	f := flag.NewFlagSet("docket-installer", flag.ContinueOnError)
	f.SetOutput(out)
	f.StringVar(&opts.Dir, "dir", "", "directory for the managed checkout")
	f.StringVar(&opts.Prefix, "prefix", "", "directory for the docket command (default ~/.local/bin)")
	f.StringVar(&opts.Checkout, "checkout", "", "install from an existing checkout without updating it")
	f.Var(&selected, "harness", "configure only this harness; repeatable")
	f.BoolVar(&opts.Project, "project", false, "put the Claude skill and Cursor rule in the current project")
	f.BoolVar(&opts.Yes, "yes", false, "apply defaults without prompts")
	f.BoolVar(&opts.NoTTY, "no-tty", false, "use plain unattended output")
	f.BoolVar(&opts.DryRun, "dry-run", false, "show every planned operation without applying it")
	f.BoolVar(&opts.Update, "update", false, "refresh Docket and its graph viewer without changing harness configuration")
	f.BoolVar(&opts.Uninstall, "uninstall", false, "remove Docket integration; keep decision ledgers")
	f.BoolVar(&opts.Version, "version", false, "show installer version")
	f.Usage = func() {
		fmt.Fprintln(out, "Usage: docket-installer [options]\n\nInstall Docket and configure agent harnesses. Docket needs Python 3.11+.")
		f.PrintDefaults()
	}
	if err := f.Parse(args); err != nil {
		return opts, err
	}
	if f.NArg() != 0 {
		return opts, fmt.Errorf("unexpected argument %q", f.Arg(0))
	}
	opts.Harness = []string(selected)
	return opts, nil
}

func main() { os.Exit(run(os.Args[1:])) }

func run(args []string) int {
	if len(args) == 1 && args[0] == "--version" {
		fmt.Println("docket-installer", version)
		return 0
	}
	opts, err := parseOptions(args, os.Stderr)
	if errors.Is(err, flag.ErrHelp) {
		return 0
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 2
	}
	if opts.Version {
		fmt.Println("docket-installer", version)
		return 0
	}
	env, err := DiscoverEnvironment(opts)
	if err != nil {
		fmt.Fprintln(os.Stderr, "docket:", err)
		return 1
	}
	interactive := !opts.Yes && !opts.NoTTY && !opts.DryRun && !opts.Update && len(opts.Harness) == 0 && term.IsTerminal(os.Stdin.Fd()) && term.IsTerminal(os.Stdout.Fd()) && os.Getenv("TERM") != "dumb"
	if interactive {
		return RunTUI(env, opts)
	}
	p, err := PreparePlan(env, opts)
	if err != nil {
		fmt.Fprintln(os.Stderr, "docket:", err)
		return 1
	}
	fmt.Println("docket installer")
	for _, note := range p.Notes {
		fmt.Println("  " + note)
	}
	for _, action := range p.Actions {
		fmt.Println("  " + DescribeAction(action))
	}
	if opts.DryRun {
		fmt.Println("Dry run: no changes applied.")
		return 0
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	err = ExecutePlan(ctx, p, func(p Progress) {
		if p.Err == nil {
			fmt.Println("  done: " + p.Action.Label)
		}
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, "docket:", err)
		if errors.Is(err, context.Canceled) {
			return 130
		}
		return 1
	}
	if opts.Uninstall {
		fmt.Println("Removed Docket integrations. Decision ledgers kept.")
	} else if opts.Update {
		fmt.Println("Updated. Run docket graph in a new shell.")
	} else {
		fmt.Println("Installed. Run docket --version in a new shell.")
	}
	return 0
}
