package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
)

func DiscoverEnvironment(opts Options) (Environment, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return Environment{}, err
	}
	cwd, err := os.Getwd()
	if err != nil {
		return Environment{}, err
	}
	e := Environment{Home: home, Cwd: cwd, GOOS: runtime.GOOS, Shell: os.Getenv("SHELL"), Path: filepath.SplitList(os.Getenv("PATH")),
		ReadFile: os.ReadFile, Readlink: os.Readlink, LookPath: exec.LookPath,
		Exists: func(p string) bool { _, err := os.Lstat(p); return err == nil }}
	e.CodexInstalled = installedCodexPlugin
	if e.Shell == "" {
		e.Shell = "/bin/sh"
	}
	e.DefaultPrefix = os.Getenv("PREFIX")
	if e.DefaultPrefix == "" {
		e.DefaultPrefix = filepath.Join(home, ".local", "bin")
	}
	e.DefaultDir = filepath.Join(home, ".local", "share", "docket")
	if xdg := os.Getenv("XDG_DATA_HOME"); xdg != "" {
		e.DefaultDir = filepath.Join(xdg, "docket")
	} else if runtime.GOOS == "windows" && os.Getenv("LOCALAPPDATA") != "" {
		e.DefaultDir = filepath.Join(os.Getenv("LOCALAPPDATA"), "docket")
	}
	e.DefaultDir, err = NormalizePath(e.DefaultDir, home, cwd)
	if err != nil {
		return e, err
	}
	e.DefaultPrefix, err = NormalizePath(e.DefaultPrefix, home, cwd)
	if err != nil {
		return e, err
	}
	e.Checkout = opts.Checkout
	if e.Checkout == "" {
		e.Checkout = opts.Dir
	}
	if e.Checkout == "" {
		e.Checkout = e.DefaultDir
	}
	e.Checkout, err = NormalizePath(e.Checkout, home, cwd)
	if err != nil {
		return e, err
	}
	if !opts.Uninstall {
		e.Python, err = findPython()
		if err != nil {
			return e, err
		}
	}
	return e, nil
}

func findPython() (string, error) {
	for _, name := range []string{"python3", "python", "py"} {
		path, err := exec.LookPath(name)
		if err != nil {
			continue
		}
		args := []string{"-I", "-c", "import json,sys; print(json.dumps({'ok': sys.version_info >= (3,11), 'executable': sys.executable}))"}
		if name == "py" {
			args = append([]string{"-3"}, args...)
		}
		out, err := exec.Command(path, args...).Output()
		if err != nil {
			continue
		}
		var result struct {
			OK         bool   `json:"ok"`
			Executable string `json:"executable"`
		}
		if json.Unmarshal(out, &result) == nil && result.OK && filepath.IsAbs(result.Executable) {
			return result.Executable, nil
		}
	}
	return "", errors.New("Python 3.11 or later is required for Docket; install Python and make python3 or python available on PATH")
}

func PreparePlan(env Environment, opts Options) (Plan, error) {
	var err error
	if opts.Prefix == "" {
		opts.Prefix = env.DefaultPrefix
	}
	opts.Prefix, err = NormalizePath(opts.Prefix, env.Home, env.Cwd)
	if err != nil {
		return Plan{}, err
	}
	checkout := opts.Checkout
	if checkout == "" {
		checkout = opts.Dir
	}
	if checkout == "" {
		checkout = env.DefaultDir
	}
	checkout, err = NormalizePath(checkout, env.Home, env.Cwd)
	if err != nil {
		return Plan{}, err
	}
	env.Checkout = checkout
	if opts.Update {
		if opts.Uninstall || opts.Project || len(opts.Harness) > 0 {
			return Plan{}, errors.New("--update cannot be combined with --uninstall, --project, or --harness")
		}
		if err := validateUpdateCommand(env, opts.Prefix); err != nil {
			return Plan{}, err
		}
	}
	if opts.Checkout != "" && !opts.Uninstall {
		if !env.Exists(filepath.Join(checkout, "bin", "docket")) {
			return Plan{}, fmt.Errorf("%s has no bin/docket", checkout)
		}
	}
	if opts.Checkout == "" && !opts.Uninstall {
		if err := validateCheckoutTarget(checkout); err != nil {
			return Plan{}, err
		}
		if checkout == env.Home || checkout == filepath.Dir(checkout) {
			return Plan{}, errors.New("choose a dedicated checkout directory")
		}
	}
	plan, err := BuildPlan(env, opts)
	if err != nil {
		return Plan{}, err
	}
	for i, action := range plan.Actions {
		if action.Kind != "write" || !env.Exists(action.Path) {
			continue
		}
		if _, err := env.Readlink(action.Path); err == nil {
			target, err := filepath.EvalSymlinks(action.Path)
			if err != nil {
				return Plan{}, fmt.Errorf("resolve %s: %w", action.Path, err)
			}
			plan.Actions[i].Path = target
		}
	}
	if opts.Checkout == "" && !opts.Uninstall {
		kind := "checkout"
		if opts.Update {
			kind = "checkout-update"
		}
		action := Action{Kind: kind, Path: checkout, Source: "https://github.com/NovusEdge/docket.git", Label: "Docket checkout"}
		if opts.Update {
			action.Source = "origin"
			if version != "dev" {
				action.Args = []string{"--tag", "v" + strings.TrimPrefix(version, "v")}
			} else {
				action.Args = []string{"--upstream"}
			}
		} else if version != "dev" {
			action.Args = []string{"--branch", "v" + strings.TrimPrefix(version, "v")}
		}
		plan.Actions = append([]Action{action}, plan.Actions...)
	}
	if !opts.Uninstall {
		viewer := join(env, checkout, "graph", "docket-graph")
		if env.GOOS == "windows" {
			viewer += ".exe"
		}
		graphSource := join(env, checkout, "graph", "go.mod")
		if opts.Checkout == "" || exists(env, graphSource) || exists(env, viewer) {
			action := Action{Kind: "viewer", Path: viewer, Source: checkout, Label: "graph viewer"}
			if len(plan.Actions) > 0 && (plan.Actions[0].Kind == "checkout" || plan.Actions[0].Kind == "checkout-update") {
				plan.Actions = append([]Action{plan.Actions[0], action}, plan.Actions[1:]...)
			} else {
				plan.Actions = append([]Action{action}, plan.Actions...)
			}
		}
	}
	return plan, nil
}

func validateUpdateCommand(env Environment, prefix string) error {
	if env.GOOS == "windows" {
		path := join(env, prefix, "docket.cmd")
		text, ok := readText(env, path)
		if !ok || !ownedWindowsShim(text, join(env, env.Checkout, "bin", "docket")) {
			return fmt.Errorf("--update requires an existing Docket command in %s", prefix)
		}
		return nil
	}
	path := join(env, prefix, "docket")
	_, err := readlink(env, path)
	if err != nil || cleanPath(env, resolvedPath(env, path)) != cleanPath(env, join(env, env.Checkout, "bin", "docket")) {
		return fmt.Errorf("--update requires an existing Docket command in %s", prefix)
	}
	return nil
}

func installedCodexPlugin() (bool, error) {
	out, err := exec.Command("codex", "plugin", "list", "--json").Output()
	if err != nil {
		return false, fmt.Errorf("check Codex plugins before uninstall: %w", err)
	}
	return parseInstalledCodex(out)
}

func parseInstalledCodex(data []byte) (bool, error) {
	var result struct {
		Installed []struct {
			ID string `json:"pluginId"`
		} `json:"installed"`
	}
	if err := json.Unmarshal(data, &result); err != nil {
		return false, fmt.Errorf("read Codex plugin list: %w", err)
	}
	if result.Installed == nil {
		return false, errors.New("Codex plugin list has no installed array")
	}
	for _, p := range result.Installed {
		if p.ID == "docket@NovusEdge" {
			return true, nil
		}
	}
	return false, nil
}
