package main

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func pathAction(t *testing.T, env Environment) Action {
	t.Helper()
	plan, err := BuildPlan(env, Options{Harness: []string{}, Prefix: "/home/a/.local/bin"})
	if err != nil {
		t.Fatal(err)
	}
	for _, a := range plan.Actions {
		if a.Label == "PATH" {
			return a
		}
	}
	t.Fatalf("no PATH action: %#v", plan.Actions)
	return Action{}
}

func TestDarwinBashTargetsLoginShellFile(t *testing.T) {
	cases := []struct {
		name     string
		existing []string
		want     string
	}{
		{"none exist", nil, "/home/a/.bash_profile"},
		{"bash_profile exists", []string{"/home/a/.bash_profile", "/home/a/.bashrc"}, "/home/a/.bash_profile"},
		{"only profile", []string{"/home/a/.profile"}, "/home/a/.profile"},
		{"login beats profile", []string{"/home/a/.bash_login", "/home/a/.profile"}, "/home/a/.bash_login"},
	}
	for _, c := range cases {
		env := testEnv(nil, c.existing...)
		env.GOOS = "darwin"
		if got := pathAction(t, env).Path; got != c.want {
			t.Errorf("%s: PATH goes to %s, want %s", c.name, got, c.want)
		}
	}
}

func TestLinuxBashStillTargetsBashrc(t *testing.T) {
	if got := pathAction(t, testEnv(nil)).Path; got != "/home/a/.bashrc" {
		t.Fatal(got)
	}
}

func TestZshHonoursZDOTDIR(t *testing.T) {
	env := testEnv(nil)
	env.Shell = "/bin/zsh"
	env.Getenv = func(k string) string {
		if k == "ZDOTDIR" {
			return "/home/a/.config/zsh"
		}
		return ""
	}
	if got := pathAction(t, env).Path; got != "/home/a/.config/zsh/.zshrc" {
		t.Fatal(got)
	}
	env.Getenv = func(string) string { return "" }
	if got := pathAction(t, env).Path; got != "/home/a/.zshrc" {
		t.Fatal(got)
	}
}

func TestUninstallFindsLegacyDarwinBashrc(t *testing.T) {
	line := "export PATH='/home/a/.local/bin':\"$PATH\""
	env := testEnv(map[string]string{"/home/a/.bashrc": "keep\n\n# added by the docket installer\n" + line + "\n"})
	env.GOOS = "darwin"
	plan, err := BuildPlan(env, Options{Prefix: "/home/a/.local/bin", Uninstall: true})
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := findAction(plan.Actions, "write", "/home/a/.bashrc"); !ok {
		t.Fatalf("legacy .bashrc entry not removed: %#v", plan.Actions)
	}
}

func TestPathApplyAppendsAndKeepsConcurrentEdits(t *testing.T) {
	rc := filepath.Join(t.TempDir(), ".bashrc")
	if err := os.WriteFile(rc, []byte("old\n"), 0600); err != nil {
		t.Fatal(err)
	}
	env := testEnv(map[string]string{rc: "old\n"})
	env.Home = filepath.Dir(rc)
	a := pathAction(t, env)
	if !a.Append || a.Path != rc {
		t.Fatalf("PATH action must append to %s: %#v", rc, a)
	}
	// Edit made after the plan was reviewed.
	if err := os.WriteFile(rc, []byte("old\nnew edit"), 0600); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 2; i++ {
		if err := executeAction(context.Background(), a); err != nil {
			t.Fatal(err)
		}
	}
	got, _ := os.ReadFile(rc)
	line := "export PATH='/home/a/.local/bin':\"$PATH\""
	if !strings.HasPrefix(string(got), "old\nnew edit\n") || strings.Count(string(got), line) != 1 {
		t.Fatalf("rc after two applies: %q", got)
	}
}

func TestPathApplyCreatesMissingFile(t *testing.T) {
	rc := filepath.Join(t.TempDir(), "sub", "config.fish")
	a := Action{Kind: "write", Path: rc, Append: true, Text: pathMarker + "\nfish_add_path '/x'\n", Label: "PATH"}
	if err := executeAction(context.Background(), a); err != nil {
		t.Fatal(err)
	}
	if got, _ := os.ReadFile(rc); string(got) != a.Text {
		t.Fatalf("%q", got)
	}
}

func TestUninstallLeavesUsersOwnHookWrapperAlone(t *testing.T) {
	env := testEnv(nil)
	own := hookCommand(env, "cursor")
	if !ownedCommand(env, own, "cursor") {
		t.Fatal("installer's own cursor command not recognised")
	}
	if ownedCommand(env, "/usr/local/bin/my-wrapper "+own, "cursor") {
		t.Fatal("wrapper containing the command was treated as owned")
	}
	if ownedCommand(env, own+" --extra", "cursor") {
		t.Fatal("extended command was treated as owned")
	}
	copilot := copilotCommand(env)
	if !ownedCommand(env, copilot, "copilot") || ownedCommand(env, "echo hi; "+copilot, "copilot") {
		t.Fatal("copilot ownership wrong")
	}
}
