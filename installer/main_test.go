package main

import (
	"bytes"
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func testEnvironment(t *testing.T) Environment {
	t.Helper()
	home := t.TempDir()
	cwd := t.TempDir()
	return Environment{Home: home, Cwd: cwd, GOOS: runtime.GOOS, Shell: "/bin/bash", Python: "/usr/bin/python3",
		DefaultDir: filepath.Join(home, ".local", "share", "docket"), DefaultPrefix: filepath.Join(home, ".local", "bin"),
		ReadFile: os.ReadFile, Readlink: os.Readlink, Exists: func(p string) bool { _, err := os.Lstat(p); return err == nil },
		LookPath: func(string) (string, error) { return "", exec.ErrNotFound }}
}

func TestParseOptionsRejectsUnknownAndAcceptsRepeatedHarnesses(t *testing.T) {
	var out bytes.Buffer
	opts, err := parseOptions([]string{"--harness", "cursor", "--harness", "gemini", "--dry-run", "--update"}, &out)
	if err != nil || len(opts.Harness) != 2 || !opts.DryRun || !opts.Update {
		t.Fatalf("%+v %v", opts, err)
	}
	if _, err := parseOptions([]string{"--harenss", "cursor"}, &out); err == nil {
		t.Fatal("unknown flag accepted")
	}
	if _, err := parseOptions([]string{"unexpected"}, &out); err == nil {
		t.Fatal("positional argument accepted")
	}
}

func TestVersionWorksWithLauncherCheckoutArgument(t *testing.T) {
	opts, err := parseOptions([]string{"--checkout", "/source", "--version"}, &bytes.Buffer{})
	if err != nil || !opts.Version {
		t.Fatalf("launcher version rejected: %+v %v", opts, err)
	}
}

func TestInstalledCodexParserMatchesExactMarketplace(t *testing.T) {
	for _, tc := range []struct {
		raw  string
		want bool
	}{
		{`{"installed":[{"pluginId":"docket@NovusEdge"}]}`, true},
		{`{"installed":[{"pluginId":"docket@local-personal"}]}`, false},
		{`{"installed":[]}`, false},
	} {
		got, err := parseInstalledCodex([]byte(tc.raw))
		if err != nil || got != tc.want {
			t.Fatalf("%s: %v %v", tc.raw, got, err)
		}
	}
	if _, err := parseInstalledCodex([]byte(`{"available":[]}`)); err == nil {
		t.Fatal("unknown plugin list schema silently accepted")
	}
}

func TestPlanResolvesSymlinkedRCAndPreservesLink(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("symlink privileges differ")
	}
	env := testEnvironment(t)
	target := filepath.Join(t.TempDir(), "bashrc")
	if err := os.WriteFile(target, []byte("alias ll='ls -l'\n"), 0600); err != nil {
		t.Fatal(err)
	}
	rc := filepath.Join(env.Home, ".bashrc")
	if err := os.Symlink(target, rc); err != nil {
		t.Fatal(err)
	}
	checkout, err := filepath.Abs("..")
	if err != nil {
		t.Fatal(err)
	}
	p, err := PreparePlan(env, Options{Checkout: checkout, Harness: []string{}})
	if err != nil {
		t.Fatal(err)
	}
	found := false
	for _, a := range p.Actions {
		if a.Kind == "write" && a.Label == "PATH" {
			if a.Path != target {
				t.Fatalf("review hides target: %s", a.Path)
			}
			found = true
		}
	}
	if !found {
		t.Fatal("PATH action missing")
	}
	if err := ExecutePlan(context.Background(), p, nil); err != nil {
		t.Fatal(err)
	}
	if got, err := os.Readlink(rc); err != nil || got != target {
		t.Fatal("dotfile symlink replaced")
	}
	if b, _ := os.ReadFile(target); !strings.Contains(string(b), "alias ll=") || !strings.Contains(string(b), "export PATH=") {
		t.Fatalf("dotfile content lost: %s", b)
	}
}

func TestStandaloneDryPlanIncludesCloneAndDoesNotWrite(t *testing.T) {
	env := testEnvironment(t)
	opts := Options{DryRun: true, Harness: []string{}}
	p, err := PreparePlan(env, opts)
	if err != nil {
		t.Fatal(err)
	}
	if len(p.Actions) == 0 || p.Actions[0].Kind != "checkout" || p.Actions[0].Path != env.DefaultDir {
		t.Fatalf("no checkout operation: %+v", p)
	}
	entries, _ := os.ReadDir(env.Home)
	if len(entries) != 0 {
		t.Fatal("planning wrote to home")
	}
}

func TestUninstallDoesNotCloneOrRequireSourceCheckout(t *testing.T) {
	env := testEnvironment(t)
	env.Python = ""
	p, err := PreparePlan(env, Options{Uninstall: true, Harness: []string{}})
	if err != nil {
		t.Fatal(err)
	}
	for _, a := range p.Actions {
		if a.Kind == "checkout" {
			t.Fatal("uninstall clones a repository")
		}
	}
}

func TestExplicitCheckoutPlanAndPrefix(t *testing.T) {
	env := testEnvironment(t)
	checkout := t.TempDir()
	if err := os.MkdirAll(filepath.Join(checkout, "bin"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(checkout, "bin", "docket"), []byte("#!/usr/bin/env python3\n"), 0755); err != nil {
		t.Fatal(err)
	}
	p, err := PreparePlan(env, Options{Checkout: checkout, Prefix: "~/my bin", Harness: []string{}})
	if err != nil {
		t.Fatal(err)
	}
	found := false
	for _, a := range p.Actions {
		if a.Kind == "checkout" {
			t.Fatal("explicit source checkout was replaced")
		}
		if a.Kind == "link" && a.Path == filepath.Join(env.Home, "my bin", "docket") {
			found = true
		}
	}
	if runtime.GOOS != "windows" && !found {
		t.Fatalf("prefix not expanded: %+v", p)
	}
}

func TestUpdatePlanOnlyRefreshesSourceAndViewer(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("source checkout path test uses Unix links")
	}
	env := testEnvironment(t)
	checkout := t.TempDir()
	if err := os.MkdirAll(filepath.Join(checkout, "bin"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(checkout, "graph"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(checkout, "bin", "docket"), []byte("#!/usr/bin/env python3\n"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(checkout, "graph", "go.mod"), []byte("module example\n"), 0644); err != nil {
		t.Fatal(err)
	}
	prefix := filepath.Join(env.Home, "bin")
	if err := os.MkdirAll(prefix, 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(checkout, "bin", "docket"), filepath.Join(prefix, "docket")); err != nil {
		t.Fatal(err)
	}
	env.Checkout = checkout
	plan, err := PreparePlan(env, Options{Checkout: checkout, Prefix: prefix, Update: true})
	if err != nil {
		t.Fatal(err)
	}
	seenViewer := false
	for _, action := range plan.Actions {
		if action.Kind == "viewer" {
			seenViewer = true
		}
		if action.Kind == "path-add" || (action.Kind == "write" && action.Label == "PATH") || action.Label == "claude-code" || action.Label == "gemini" {
			t.Fatalf("update planned unrelated action: %#v", action)
		}
	}
	if !seenViewer {
		t.Fatalf("update did not plan viewer refresh: %#v", plan.Actions)
	}
}

func TestUpdateRejectsIntegrationOptions(t *testing.T) {
	env := testEnvironment(t)
	checkout := t.TempDir()
	if err := os.MkdirAll(filepath.Join(checkout, "bin"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(checkout, "bin", "docket"), []byte("source"), 0755); err != nil {
		t.Fatal(err)
	}
	prefix := filepath.Join(env.Home, "bin")
	if err := os.MkdirAll(prefix, 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(checkout, "bin", "docket"), filepath.Join(prefix, "docket")); err != nil {
		t.Fatal(err)
	}
	for _, opts := range []Options{
		{Update: true, Uninstall: true},
		{Update: true, Project: true},
		{Update: true, Harness: []string{"claude-code"}},
	} {
		opts.Checkout, opts.Prefix = checkout, prefix
		if _, err := PreparePlan(env, opts); err == nil || !strings.Contains(err.Error(), "--update") {
			t.Fatalf("options %#v accepted: %v", opts, err)
		}
	}
}

func TestUpdateRequiresAnOwnedInstalledCommand(t *testing.T) {
	env := testEnvironment(t)
	checkout := t.TempDir()
	if err := os.MkdirAll(filepath.Join(checkout, "bin"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(checkout, "bin", "docket"), []byte("source"), 0755); err != nil {
		t.Fatal(err)
	}
	_, err := PreparePlan(env, Options{Checkout: checkout, Prefix: filepath.Join(env.Home, "bin"), Update: true})
	if err == nil || !strings.Contains(err.Error(), "existing Docket command") {
		t.Fatalf("missing installed command accepted: %v", err)
	}
}

func TestManagedUpdateRefreshesCheckoutBeforeViewer(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("source checkout path test uses Unix links")
	}
	env := testEnvironment(t)
	checkout := t.TempDir()
	if err := os.MkdirAll(filepath.Join(checkout, "bin"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(checkout, "graph"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(checkout, "bin", "docket"), []byte("source"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(checkout, "graph", "go.mod"), []byte("module example\n"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(checkout, "VERSION"), []byte("1.2.3\n"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := runGit(checkout, "init"); err != nil {
		t.Fatal(err)
	}
	if err := runGit(checkout, "remote", "add", "origin", "https://github.com/NovusEdge/docket.git"); err != nil {
		t.Fatal(err)
	}
	env.DefaultDir = checkout
	prefix := filepath.Join(env.Home, "bin")
	if err := os.MkdirAll(prefix, 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(checkout, "bin", "docket"), filepath.Join(prefix, "docket")); err != nil {
		t.Fatal(err)
	}
	plan, err := PreparePlan(env, Options{Prefix: prefix, Update: true, Harness: []string{}})
	if err != nil {
		t.Fatal(err)
	}
	if len(plan.Actions) < 2 || plan.Actions[0].Kind != "checkout-update" || plan.Actions[1].Kind != "viewer" {
		t.Fatalf("managed update order = %#v", plan.Actions)
	}
}

func TestInstallUninstallRoundTripInTemporaryHome(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("native Windows integration needs registry isolation")
	}
	env := testEnvironment(t)
	checkout, err := filepath.Abs("..")
	if err != nil {
		t.Fatal(err)
	}
	python, err := exec.LookPath("python3")
	if err != nil {
		t.Skip("Python unavailable")
	}
	env.Python = python
	opts := Options{Checkout: checkout, Harness: []string{"gemini", "cursor", "copilot", "opencode"}}
	p, err := PreparePlan(env, opts)
	if err != nil {
		t.Fatal(err)
	}
	if err := ExecutePlan(context.Background(), p, nil); err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command(filepath.Join(env.DefaultPrefix, "docket"), "--version")
	cmd.Env = []string{"HOME=" + env.Home, "PATH=" + filepath.Dir(python) + ":/usr/bin:/bin"}
	if out, err := cmd.CombinedOutput(); err != nil || !strings.Contains(string(out), "docket") {
		t.Fatalf("installed command failed: %s %v", out, err)
	}
	opts.Uninstall = true
	p, err = PreparePlan(env, opts)
	if err != nil {
		t.Fatal(err)
	}
	if err := ExecutePlan(context.Background(), p, nil); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Lstat(filepath.Join(env.DefaultPrefix, "docket")); !os.IsNotExist(err) {
		t.Fatal("command left after uninstall")
	}
}
