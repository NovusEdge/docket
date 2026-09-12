package main

import (
	"errors"
	"io/fs"
	"strings"
	"syscall"
	"testing"
)

func testEnv(files map[string]string, existing ...string) Environment {
	present := map[string]bool{}
	for _, p := range existing {
		present[p] = true
	}
	return Environment{
		Home: "/home/a", Cwd: "/work/project", GOOS: "linux", Shell: "/bin/bash",
		Python: "/usr/bin/python3", Checkout: "/src/docket", DefaultPrefix: "/home/a/.local/bin",
		Path:   []string{"/usr/bin"},
		Exists: func(p string) bool { return present[p] },
		ReadFile: func(p string) ([]byte, error) {
			if s, ok := files[p]; ok {
				return []byte(s), nil
			}
			return nil, fs.ErrNotExist
		},
		Readlink: func(p string) (string, error) { return "", fs.ErrNotExist },
	}
}

func TestReadErrorsNeverProduceAWritePlan(t *testing.T) {
	tests := []struct {
		name, denied string
		opts         Options
	}{
		{"shell rc", "/home/a/.bashrc", Options{Harness: []string{}, Prefix: "/home/a/.local/bin"}},
		{"JSON config", "/home/a/.gemini/settings.json", Options{Harness: []string{"gemini"}, Prefix: "/usr/bin"}},
		{"OpenCode plugin", "/home/a/.config/opencode/plugins/docket/index.ts", Options{Harness: []string{"opencode"}, Prefix: "/usr/bin"}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			env := testEnv(nil)
			env.ReadFile = func(p string) ([]byte, error) {
				if p == tt.denied {
					return nil, fs.ErrPermission
				}
				return nil, fs.ErrNotExist
			}
			plan, err := BuildPlan(env, tt.opts)
			if !errors.Is(err, fs.ErrPermission) {
				t.Fatalf("error = %v", err)
			}
			if len(plan.Actions) != 0 || len(plan.Notes) != 0 {
				t.Fatalf("non-empty plan on read error: %#v", plan)
			}
		})
	}
	env := testEnv(nil)
	env.Readlink = func(string) (string, error) { return "", fs.ErrPermission }
	plan, err := BuildPlan(env, Options{Harness: []string{}, Prefix: "/usr/bin"})
	if !errors.Is(err, fs.ErrPermission) {
		t.Fatalf("readlink error = %v", err)
	}
	if len(plan.Actions) != 0 {
		t.Fatalf("non-empty plan on readlink error: %#v", plan)
	}
}

func TestRegularFilesAtLinkTargetsArePreserved(t *testing.T) {
	env := testEnv(nil, "/usr/bin/docket", "/home/a/.claude/skills/docket")
	env.Readlink = func(string) (string, error) { return "", syscall.EINVAL }
	plan, err := BuildPlan(env, Options{Harness: []string{"claude-code"}, Prefix: "/usr/bin"})
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := findAction(plan.Actions, "link", "/usr/bin/docket"); ok {
		t.Fatal("unrelated regular command would be overwritten")
	}
	if _, ok := findAction(plan.Actions, "link", "/home/a/.claude/skills/docket"); ok {
		t.Fatal("unrelated regular Claude file would be overwritten")
	}
}

func TestWindowsNonReparsePointAtClaudeTargetIsPreserved(t *testing.T) {
	env := testEnv(nil, `C:\Users\A\.claude\skills\docket`)
	env.GOOS, env.Home, env.Checkout, env.Python = "windows", `C:\Users\A`, `C:\src\docket`, `C:\Python\python.exe`
	env.Readlink = func(string) (string, error) { return "", syscall.Errno(4390) }
	plan, err := BuildPlan(env, Options{Harness: []string{"claude-code"}, Prefix: `C:\Tools`})
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := findAction(plan.Actions, "link", `C:\Users\A\.claude\skills\docket`); ok {
		t.Fatal("normal Windows directory would be overwritten")
	}
}

func findAction(actions []Action, kind, path string) (Action, bool) {
	for _, a := range actions {
		if a.Kind == kind && a.Path == path {
			return a, true
		}
	}
	return Action{}, false
}

func TestExplicitEmptyHarnessSelectionStillInstallsCommandOnly(t *testing.T) {
	env := testEnv(map[string]string{"/home/a/.bashrc": "export EDITOR=vim\n"}, "/home/a/.claude")
	plan, err := BuildPlan(env, Options{Prefix: "/home/a/.local/bin", Harness: []string{}})
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := findAction(plan.Actions, "link", "/home/a/.local/bin/docket"); !ok {
		t.Fatal("missing command link")
	}
	if _, ok := findAction(plan.Actions, "link", "/home/a/.claude/skills/docket"); ok {
		t.Fatal("explicit empty selection configured Claude")
	}
	for _, a := range plan.Actions {
		if a.Kind == "command" {
			t.Fatalf("unexpected harness command: %#v", a)
		}
	}
}

func TestNilSelectionDetectsHarnessesAndKeepsClaudeDefault(t *testing.T) {
	env := testEnv(map[string]string{}, "/home/a/.gemini")
	plan, err := BuildPlan(env, Options{Prefix: "/home/a/.local/bin"})
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := findAction(plan.Actions, "link", "/home/a/.claude/skills/docket"); !ok {
		t.Fatal("Claude is the legacy default")
	}
	if _, ok := findAction(plan.Actions, "write", "/home/a/.gemini/settings.json"); !ok {
		t.Fatal("detected Gemini was not configured")
	}
	if _, ok := findAction(plan.Actions, "write", "/home/a/.cursor/hooks.json"); ok {
		t.Fatal("undetected Cursor was configured")
	}
}

func TestUnknownHarnessIsRejected(t *testing.T) {
	_, err := BuildPlan(testEnv(nil), Options{Harness: []string{"unknown"}})
	if err == nil || !strings.Contains(err.Error(), "unknown harness") {
		t.Fatalf("got %v", err)
	}
}

func TestMalformedSelectedHarnessJSONIsRejected(t *testing.T) {
	env := testEnv(map[string]string{"/home/a/.gemini/settings.json": "{"}, "/home/a/.gemini")
	_, err := BuildPlan(env, Options{Harness: []string{"gemini"}})
	if err == nil || !strings.Contains(err.Error(), "/home/a/.gemini/settings.json") {
		t.Fatalf("got %v", err)
	}
}

func TestGeminiMergePreservesUnrelatedConfigurationAndIsIdempotent(t *testing.T) {
	original := `{"theme":"dark","hooks":{"SessionStart":[{"name":"other","hooks":[]}]}}`
	env := testEnv(map[string]string{"/home/a/.gemini/settings.json": original}, "/home/a/.gemini")
	plan, err := BuildPlan(env, Options{Harness: []string{"gemini"}, Prefix: "/usr/bin"})
	if err != nil {
		t.Fatal(err)
	}
	a, ok := findAction(plan.Actions, "write", "/home/a/.gemini/settings.json")
	if !ok || !strings.Contains(a.Text, `"theme": "dark"`) || !strings.Contains(a.Text, `"name": "other"`) || !strings.Contains(a.Text, `"name": "docket"`) {
		t.Fatalf("bad merge: %#v", a)
	}
	env2 := testEnv(map[string]string{"/home/a/.gemini/settings.json": a.Text}, "/home/a/.gemini")
	second, err := BuildPlan(env2, Options{Harness: []string{"gemini"}, Prefix: "/usr/bin"})
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := findAction(second.Actions, "write", "/home/a/.gemini/settings.json"); ok {
		t.Fatal("idempotent plan rewrote Gemini settings")
	}
}

func TestCodexCommandsAreReviewableActions(t *testing.T) {
	env := testEnv(nil)
	env.LookPath = func(name string) (string, error) { return "/usr/bin/codex", nil }
	plan, err := BuildPlan(env, Options{Harness: []string{"codex"}, Prefix: "/usr/bin"})
	if err != nil {
		t.Fatal(err)
	}
	commands := []Action{}
	for _, action := range plan.Actions {
		if action.Kind == "command" {
			commands = append(commands, action)
		}
	}
	if len(commands) != 2 {
		t.Fatalf("actions = %#v", plan.Actions)
	}
	if got := strings.Join(commands[0].Args, "|"); got != "codex|plugin|marketplace|add|/src/docket" {
		t.Fatalf("first command = %q", got)
	}
	if got := strings.Join(commands[1].Args, "|"); got != "codex|plugin|add|docket@NovusEdge" {
		t.Fatalf("second command = %q", got)
	}
}

func TestExplicitCodexRequiresTheCLI(t *testing.T) {
	_, err := BuildPlan(testEnv(nil), Options{Harness: []string{"codex"}, Prefix: "/usr/bin"})
	if err == nil || !strings.Contains(err.Error(), "codex") || !strings.Contains(err.Error(), "PATH") {
		t.Fatalf("got %v", err)
	}
}

func TestCodexUninstallUsesInstalledDiscovery(t *testing.T) {
	env := testEnv(nil)
	env.LookPath = func(string) (string, error) { return "/usr/bin/codex", nil }
	env.CodexInstalled = func() (bool, error) { return true, nil }
	plan, err := BuildPlan(env, Options{Prefix: "/usr/bin", Uninstall: true})
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := findAction(plan.Actions, "command", ""); !ok {
		t.Fatal("legacy installed Codex plugin was not removed")
	}

	env.CodexInstalled = func() (bool, error) { return false, nil }
	plan, err = BuildPlan(env, Options{Prefix: "/usr/bin", Uninstall: true})
	if err != nil {
		t.Fatal(err)
	}
	for _, action := range plan.Actions {
		if action.Kind == "command" && action.Label == "codex" {
			t.Fatal("absent Codex plugin removal was planned")
		}
	}

	env.CodexInstalled = func() (bool, error) { return false, fs.ErrPermission }
	plan, err = BuildPlan(env, Options{Prefix: "/usr/bin", Uninstall: true})
	if !errors.Is(err, fs.ErrPermission) || len(plan.Actions) != 0 {
		t.Fatalf("plan=%#v err=%v", plan, err)
	}
}

func TestWindowsUsesCmdShimAndRegistryPathAction(t *testing.T) {
	env := testEnv(nil)
	env.GOOS, env.Home, env.Checkout, env.Python, env.Path = "windows", `C:\Users\A`, `C:\Source Folder\docket`, `C:\Python 3\python.exe`, nil
	plan, err := BuildPlan(env, Options{Harness: []string{}, Prefix: `C:\Tools Folder`})
	if err != nil {
		t.Fatal(err)
	}
	shim, ok := findAction(plan.Actions, "write", `C:\Tools Folder\docket.cmd`)
	if !ok || shim.Text != "@echo off\r\n\"C:\\Python 3\\python.exe\" \"C:\\Source Folder\\docket\\bin\\docket\" %*\r\n" {
		t.Fatalf("shim = %#v", shim)
	}
	pathAction, ok := findAction(plan.Actions, "path-add", `C:\Tools Folder`)
	if !ok {
		t.Fatalf("missing Windows path action: %#v", plan.Actions)
	}
	if pathAction.Source != `C:\Tools Folder\.docket-path.json` || !strings.Contains(pathAction.Text, `"checkout": "C:\\Source Folder\\docket"`) {
		t.Fatalf("PATH receipt metadata missing: %#v", pathAction)
	}
	for _, action := range plan.Actions {
		if action.Kind == "write" && action.Path == pathAction.Source {
			t.Fatal("receipt must be coupled to path-add")
		}
	}
	for _, a := range plan.Actions {
		if strings.HasSuffix(a.Path, ".bashrc") {
			t.Fatal("Windows plan touched shell rc")
		}
	}
}

func TestUninstallRemovesOnlyOwnedArtifactsAndPreservesLedger(t *testing.T) {
	files := map[string]string{
		"/home/a/.bashrc": "keep\n# added by the docket installer\nexport PATH='/home/a/.local/bin':\"$PATH\"\n",
		"/home/a/.config/opencode/plugins/docket/index.ts": "user file",
	}
	env := testEnv(files, "/home/a/.local/bin/docket", "/home/a/.claude/skills/docket", "/home/a/.config/opencode/plugins/docket/index.ts", "/work/project/.docket/ledger.jsonl")
	env.Readlink = func(p string) (string, error) {
		if p == "/home/a/.local/bin/docket" {
			return "/some/other/tool", nil
		}
		if p == "/home/a/.claude/skills/docket" {
			return "/src/docket", nil
		}
		return "", fs.ErrNotExist
	}
	plan, err := BuildPlan(env, Options{Prefix: "/home/a/.local/bin", Uninstall: true})
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := findAction(plan.Actions, "remove", "/home/a/.local/bin/docket"); ok {
		t.Fatal("removed an unowned command")
	}
	if _, ok := findAction(plan.Actions, "remove", "/home/a/.claude/skills/docket"); !ok {
		t.Fatal("did not remove owned Claude link")
	}
	if _, ok := findAction(plan.Actions, "remove", "/home/a/.config/opencode/plugins/docket/index.ts"); ok {
		t.Fatal("removed unowned OpenCode file")
	}
	for _, a := range plan.Actions {
		if strings.Contains(a.Path, "ledger") {
			t.Fatalf("ledger action: %#v", a)
		}
	}
}

func TestProjectUninstallRemovesOwnedCursorRule(t *testing.T) {
	rule := "/work/project/.cursor/rules/docket.mdc"
	text := "---\nalwaysApply: true\n---\n\nSee docket's skill for when and how to record a decision.\n"
	env := testEnv(map[string]string{rule: text})
	plan, err := BuildPlan(env, Options{Prefix: "/usr/bin", Project: true, Uninstall: true})
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := findAction(plan.Actions, "remove", rule); !ok {
		t.Fatalf("owned project rule was retained: %#v", plan.Actions)
	}
}

func TestUninstallOwnershipDoesNotRequirePythonDiscovery(t *testing.T) {
	installed := testEnv(nil)
	installed.GOOS, installed.Home, installed.Checkout, installed.Python = "windows", `C:\Users\A`, `C:\src\docket`, `C:\Python\python.exe`
	shim := "@echo off\r\n\"C:\\Python\\python.exe\" \"C:\\src\\docket\\bin\\docket\" %*\r\n"
	plugin := openCodeSource(installed)
	installed.Python = ""
	installed.ReadFile = func(p string) ([]byte, error) {
		switch p {
		case `C:\Tools\docket.cmd`:
			return []byte(shim), nil
		case `C:\Users\A\.config\opencode\plugins\docket\index.ts`:
			return []byte(plugin), nil
		}
		return nil, fs.ErrNotExist
	}
	plan, err := BuildPlan(installed, Options{Prefix: `C:\Tools`, Uninstall: true})
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := findAction(plan.Actions, "remove", `C:\Tools\docket.cmd`); !ok {
		t.Fatal("owned shim was not recognized")
	}
	if _, ok := findAction(plan.Actions, "remove", `C:\Users\A\.config\opencode\plugins\docket\index.ts`); !ok {
		t.Fatal("owned plugin was not recognized")
	}
}

func TestWindowsPathRemovalRequiresInstallerReceipt(t *testing.T) {
	env := testEnv(nil)
	env.GOOS, env.Home, env.Checkout, env.Path = "windows", `C:\Users\A`, `C:\src\docket`, []string{`C:\Tools`}
	without, err := BuildPlan(env, Options{Prefix: `C:\Tools`, Uninstall: true})
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := findAction(without.Actions, "path-remove", `C:\Tools`); ok {
		t.Fatal("removed PATH entry without ownership receipt")
	}
	receipt := "{\n  \"checkout\": \"C:\\\\src\\\\docket\",\n  \"directory\": \"C:\\\\Tools\"\n}\n"
	env.ReadFile = func(p string) ([]byte, error) {
		if p == `C:\Tools\.docket-path.json` {
			return []byte(receipt), nil
		}
		return nil, fs.ErrNotExist
	}
	with, err := BuildPlan(env, Options{Prefix: `C:\Tools`, Uninstall: true})
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := findAction(with.Actions, "path-remove", `C:\Tools`); !ok {
		t.Fatal("matching receipt did not authorize PATH removal")
	}
	if _, ok := findAction(with.Actions, "remove", `C:\Tools\.docket-path.json`); !ok {
		t.Fatal("receipt was not cleaned up")
	}
}

func TestShellPathRemovalRequiresAdjacentOwnershipMarker(t *testing.T) {
	line := "export PATH='/home/a/.local/bin':\"$PATH\""
	env := testEnv(map[string]string{"/home/a/.bashrc": line + "\n# added by the docket installer\nkeep\n"})
	plan, err := BuildPlan(env, Options{Prefix: "/home/a/.local/bin", Uninstall: true})
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := findAction(plan.Actions, "write", "/home/a/.bashrc"); ok {
		t.Fatal("removed an unpaired user PATH line")
	}
}

func TestShellHelpersQuoteSpacesAndComparePathEntries(t *testing.T) {
	if got := ShellRC(Environment{Home: "/home/a", Shell: "/bin/fish"}); got != "/home/a/.config/fish/config.fish" {
		t.Fatal(got)
	}
	if got := RCLine("/bin/bash", "/home/a/My Bin"); got != "export PATH='/home/a/My Bin':\"$PATH\"" {
		t.Fatal(got)
	}
	if !PathContains([]string{"/x", "/home/a/My Bin/"}, "/home/a/My Bin", "linux") {
		t.Fatal("path entry not matched")
	}
	if PathContains([]string{"/home/a/My Binx"}, "/home/a/My Bin", "linux") {
		t.Fatal("substring matched")
	}
	if !PathContains([]string{`c:\TOOLS\`}, `C:\Tools`, "windows") {
		t.Fatal("Windows comparison should fold case")
	}
}
