package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"path"
	"strings"
	"syscall"
)

const pathMarker = "# added by the docket installer"

var harnessNames = []string{"claude-code", "codex", "gemini", "cursor", "copilot", "opencode"}

func BuildPlan(env Environment, opts Options) (Plan, error) {
	var readErr error
	readFile := env.ReadFile
	if readFile != nil {
		env.ReadFile = func(path string) ([]byte, error) {
			data, err := readFile(path)
			if err != nil && !errors.Is(err, fs.ErrNotExist) && readErr == nil {
				readErr = fmt.Errorf("read %s: %w", path, err)
			}
			return data, err
		}
	}
	readlinkFn := env.Readlink
	if readlinkFn != nil {
		env.Readlink = func(path string) (string, error) {
			target, err := readlinkFn(path)
			if err != nil && !isNotLinkError(env.GOOS, err) && readErr == nil {
				readErr = fmt.Errorf("read link %s: %w", path, err)
			}
			return target, err
		}
	}
	plan, err := buildPlan(env, opts)
	if readErr != nil {
		return Plan{}, readErr
	}
	return plan, err
}

func isNotLinkError(goos string, err error) bool {
	if errors.Is(err, fs.ErrNotExist) {
		return true
	}
	if goos == "windows" {
		return errors.Is(err, syscall.Errno(4390)) // ERROR_NOT_A_REPARSE_POINT
	}
	return errors.Is(err, fs.ErrInvalid) || errors.Is(err, syscall.EINVAL)
}

func buildPlan(env Environment, opts Options) (Plan, error) {
	if env.Checkout == "" {
		env.Checkout = opts.Checkout
	}
	prefix := opts.Prefix
	if prefix == "" {
		prefix = env.DefaultPrefix
	}
	if env.Checkout == "" {
		return Plan{}, fmt.Errorf("checkout is required")
	}
	if prefix == "" {
		return Plan{}, fmt.Errorf("prefix is required")
	}

	selected := opts.Harness
	if selected != nil {
		known := map[string]bool{}
		for _, name := range harnessNames {
			known[name] = true
		}
		for _, name := range selected {
			if !known[name] {
				return Plan{}, fmt.Errorf("unknown harness %q", name)
			}
		}
	}
	if opts.Uninstall {
		return buildUninstall(env, prefix, opts.Project)
	}
	if opts.Update {
		return Plan{}, nil
	}

	plan := Plan{}
	plan.Actions = append(plan.Actions, planCommand(env, prefix)...)
	plan.Actions = append(plan.Actions, planPathAdd(env, prefix)...)
	if selected == nil {
		selected = []string{"claude-code"}
		for _, h := range DetectHarnesses(env) {
			if h.Detected && h.Name != "claude-code" {
				selected = append(selected, h.Name)
			}
		}
	}
	seen := map[string]bool{}
	for _, name := range selected {
		if seen[name] {
			continue
		}
		seen[name] = true
		actions, err := planHarness(env, opts.Project, name, prefix)
		if err != nil {
			return Plan{}, err
		}
		plan.Actions = append(plan.Actions, actions...)
	}
	return plan, nil
}

func DetectHarnesses(env Environment) []Harness {
	dirs := map[string]string{
		"claude-code": join(env, env.Home, ".claude"),
		"gemini":      join(env, env.Home, ".gemini"),
		"cursor":      join(env, env.Home, ".cursor"),
		"copilot":     join(env, env.Home, ".copilot"),
		"opencode":    join(env, env.Home, ".config", "opencode"),
	}
	out := make([]Harness, 0, len(harnessNames))
	for _, name := range harnessNames {
		detected, detail := false, "not found"
		if name == "codex" || name == "copilot" {
			if commandPresent(env, name) {
				detected, detail = true, "command on PATH"
			}
		}
		if dir := dirs[name]; !detected && dir != "" && exists(env, dir) {
			detected, detail = true, dir
		}
		out = append(out, Harness{Name: name, Detected: detected, Detail: detail})
	}
	return out
}

func planCommand(env Environment, prefix string) []Action {
	source := join(env, env.Checkout, "bin", "docket")
	if env.GOOS == "windows" {
		target := join(env, prefix, "docket.cmd")
		text := fmt.Sprintf("@echo off\r\n\"%s\" \"%s\" %%*\r\n", env.Python, source)
		if sameFile(env, target, text) {
			return nil
		}
		return []Action{{Kind: "write", Path: target, Text: text, Label: "command"}}
	}
	target := join(env, prefix, "docket")
	if link, err := readlink(env, target); err == nil {
		if link == source {
			return nil
		}
		return []Action{{Kind: "link", Path: target, Source: source, Label: "command"}}
	}
	if exists(env, target) {
		return nil
	}
	return []Action{{Kind: "link", Path: target, Source: source, Label: "command"}}
}

func planPathAdd(env Environment, prefix string) []Action {
	if PathContains(env.Path, prefix, env.GOOS) {
		return nil
	}
	if env.GOOS == "windows" {
		receiptPath := join(env, prefix, ".docket-path.json")
		receipt, _ := json.MarshalIndent(map[string]string{"checkout": env.Checkout, "directory": prefix}, "", "  ")
		return []Action{{Kind: "path-add", Path: prefix, Source: receiptPath, Text: string(receipt) + "\n", Label: "PATH"}}
	}
	rc := resolvedPath(env, ShellRC(env))
	line := RCLine(env.Shell, prefix)
	existing, _ := readText(env, rc)
	for _, got := range strings.Split(existing, "\n") {
		if strings.TrimSpace(got) == line {
			return nil
		}
	}
	var add string
	if existing != "" && !strings.HasSuffix(existing, "\n") {
		add += "\n"
	}
	if existing != "" {
		add += "\n"
	}
	add += pathMarker + "\n" + line + "\n"
	return []Action{{Kind: "write", Path: rc, Text: existing + add, Label: "PATH"}}
}

func planHarness(env Environment, project bool, name, prefix string) ([]Action, error) {
	switch name {
	case "claude-code":
		return planClaude(env, project)
	case "codex":
		if !commandPresent(env, "codex") {
			return nil, fmt.Errorf("codex harness selected, but codex was not found on PATH")
		}
		receiptPath := join(env, prefix, ".docket-codex.json")
		receipt := codexReceipt(env)
		actions := []Action{
			{Kind: "command", Args: []string{"codex", "plugin", "marketplace", "add", env.Checkout}, Label: "codex"},
			{Kind: "command", Args: []string{"codex", "plugin", "add", "docket@NovusEdge"}, Label: "codex"},
		}
		if !sameFile(env, receiptPath, receipt) {
			actions = append(actions, Action{Kind: "write", Path: receiptPath, Text: receipt, Label: "codex"})
		}
		return actions, nil
	case "gemini":
		return planGemini(env)
	case "cursor":
		return planCursor(env, project)
	case "copilot":
		return planCopilot(env)
	case "opencode":
		return planOpenCode(env), nil
	default:
		return nil, fmt.Errorf("unknown harness %q", name)
	}
}

func planClaude(env Environment, project bool) ([]Action, error) {
	plugins := join(env, env.Home, ".claude", "plugins", "installed_plugins.json")
	if text, ok := readText(env, plugins); ok {
		data, err := parseObject(plugins, text)
		if err != nil {
			return nil, err
		}
		if entries, ok := data["plugins"].(map[string]any); ok {
			for key := range entries {
				if strings.SplitN(key, "@", 2)[0] == "docket" {
					return nil, nil
				}
			}
		}
	}
	base := env.Home
	if project {
		base = env.Cwd
		if cleanPath(env, base) == cleanPath(env, env.Checkout) {
			return nil, nil
		}
	}
	target := join(env, base, ".claude", "skills", "docket")
	if link, err := readlink(env, target); err == nil && cleanPath(env, link) == cleanPath(env, env.Checkout) {
		return nil, nil
	}
	if exists(env, target) {
		return nil, nil
	}
	return []Action{{Kind: "link", Path: target, Source: env.Checkout, Label: "claude-code"}}, nil
}

func planGemini(env Environment) ([]Action, error) {
	p := join(env, env.Home, ".gemini", "settings.json")
	data, err := loadObject(env, p)
	if err != nil {
		return nil, err
	}
	entry := map[string]any{"name": "docket", "hooks": []any{map[string]any{"type": "command", "command": hookCommand(env, "gemini"), "timeout": float64(5000)}}}
	changed, err := mergeNestedHook(data, "SessionStart", entry, func(v map[string]any) bool { return v["name"] == "docket" })
	if err != nil {
		return nil, fmt.Errorf("%s: %w", p, err)
	}
	if !changed {
		return nil, nil
	}
	return jsonWrite(p, data, "gemini")
}

func planCursor(env Environment, project bool) ([]Action, error) {
	p := join(env, env.Home, ".cursor", "hooks.json")
	data, err := loadObject(env, p)
	if err != nil {
		return nil, err
	}
	entry := map[string]any{"command": hookCommand(env, "cursor")}
	changed, err := mergeNestedHook(data, "sessionStart", entry, func(v map[string]any) bool { return ownedCommand(env, stringValue(v["command"])) })
	if err != nil {
		return nil, fmt.Errorf("%s: %w", p, err)
	}
	if _, ok := data["version"]; !ok {
		data["version"] = float64(1)
		changed = true
	}
	actions := []Action{}
	if changed {
		actions, _ = jsonWrite(p, data, "cursor")
	}
	if project {
		rule := join(env, env.Cwd, ".cursor", "rules", "docket.mdc")
		text := cursorRuleText()
		if !sameFile(env, rule, text) {
			actions = append(actions, Action{Kind: "write", Path: rule, Text: text, Label: "cursor"})
		}
	}
	return actions, nil
}

func planCopilot(env Environment) ([]Action, error) {
	p := join(env, env.Home, ".copilot", "hooks", "sessionStart.json")
	data, err := loadObject(env, p)
	if err != nil {
		return nil, err
	}
	docket := join(env, env.Checkout, "bin", "docket")
	entry := map[string]any{
		"type": "command", "bash": "DOCKET_AUTHOR=copilot " + posixRun(env, docket) + " context --for copilot",
		"powershell": fmt.Sprintf("$env:DOCKET_AUTHOR=\"copilot\"; & \"%s\" \"%s\" context --for copilot", env.Python, docket), "timeoutSec": float64(5),
	}
	changed, err := mergeNestedHook(data, "sessionStart", entry, func(v map[string]any) bool { return ownedCommand(env, stringValue(v["bash"])) })
	if err != nil {
		return nil, fmt.Errorf("%s: %w", p, err)
	}
	if _, ok := data["version"]; !ok {
		data["version"] = float64(1)
		changed = true
	}
	if !changed {
		return nil, nil
	}
	return jsonWrite(p, data, "copilot")
}

func planOpenCode(env Environment) []Action {
	p := join(env, env.Home, ".config", "opencode", "plugins", "docket", "index.ts")
	text := openCodeSource(env)
	if sameFile(env, p, text) {
		return nil
	}
	return []Action{{Kind: "write", Path: p, Text: text, Label: "opencode"}}
}

func buildUninstall(env Environment, prefix string, project bool) (Plan, error) {
	plan := Plan{Notes: []string{"Decision ledgers are preserved."}}
	source := join(env, env.Checkout, "bin", "docket")
	if env.GOOS == "windows" {
		p := join(env, prefix, "docket.cmd")
		if text, ok := readText(env, p); ok && ownedWindowsShim(text, source) {
			plan.Actions = append(plan.Actions, Action{Kind: "remove", Path: p, Label: "command"})
		}
		receiptPath := join(env, prefix, ".docket-path.json")
		if text, ok := readText(env, receiptPath); ok {
			var receipt struct{ Directory, Checkout string }
			if err := json.Unmarshal([]byte(text), &receipt); err != nil {
				return Plan{}, fmt.Errorf("%s: malformed JSON: %w", receiptPath, err)
			}
			if cleanPath(env, receipt.Directory) == cleanPath(env, prefix) && cleanPath(env, receipt.Checkout) == cleanPath(env, env.Checkout) {
				plan.Actions = append(plan.Actions, Action{Kind: "path-remove", Path: prefix, Label: "PATH"})
				plan.Actions = append(plan.Actions, Action{Kind: "remove", Path: receiptPath, Label: "PATH"})
			}
		}
	} else {
		p := join(env, prefix, "docket")
		if link, err := readlink(env, p); err == nil && cleanPath(env, link) == cleanPath(env, source) {
			plan.Actions = append(plan.Actions, Action{Kind: "remove", Path: p, Label: "command"})
		}
		plan.Actions = append(plan.Actions, planPathRemove(env, prefix)...)
	}
	claudeBase := env.Home
	if project {
		claudeBase = env.Cwd
	}
	p := join(env, claudeBase, ".claude", "skills", "docket")
	if link, err := readlink(env, p); err == nil && cleanPath(env, link) == cleanPath(env, env.Checkout) {
		plan.Actions = append(plan.Actions, Action{Kind: "remove", Path: p, Label: "claude-code"})
	}
	var err error
	plan.Actions, err = uninstallJSONHooks(env, plan.Actions)
	if err != nil {
		return Plan{}, err
	}
	oc := join(env, env.Home, ".config", "opencode", "plugins", "docket", "index.ts")
	if text, ok := readText(env, oc); ok && ownedOpenCode(env, text) {
		plan.Actions = append(plan.Actions, Action{Kind: "remove", Path: oc, Label: "opencode"})
	}
	if project {
		rule := join(env, env.Cwd, ".cursor", "rules", "docket.mdc")
		if text, ok := readText(env, rule); ok && text == cursorRuleText() {
			plan.Actions = append(plan.Actions, Action{Kind: "remove", Path: rule, Label: "cursor"})
		}
	}
	codexReceiptPath := join(env, prefix, ".docket-codex.json")
	receiptText, hasReceipt := readText(env, codexReceiptPath)
	hasReceipt = hasReceipt && receiptText == codexReceipt(env)
	codexPresent := commandPresent(env, "codex")
	codexInstalled := false
	if codexPresent && env.CodexInstalled != nil {
		var err error
		codexInstalled, err = env.CodexInstalled()
		if err != nil {
			return Plan{}, fmt.Errorf("detect installed Codex plugin: %w", err)
		}
	} else if codexPresent && hasReceipt {
		codexInstalled = true
	}
	if codexInstalled {
		plan.Actions = append(plan.Actions, Action{Kind: "command", Args: []string{"codex", "plugin", "remove", "docket@NovusEdge"}, Label: "codex"})
	}
	if hasReceipt {
		if codexPresent {
			plan.Actions = append(plan.Actions, Action{Kind: "remove", Path: codexReceiptPath, Label: "codex"})
		} else {
			plan.Notes = append(plan.Notes, "Codex is not on PATH; its plugin registration was left in place.")
		}
	}
	return plan, nil
}

func uninstallJSONHooks(env Environment, actions []Action) ([]Action, error) {
	types := []struct {
		path, event, label string
		match              func(map[string]any) bool
	}{
		{join(env, env.Home, ".gemini", "settings.json"), "SessionStart", "gemini", func(v map[string]any) bool { return v["name"] == "docket" }},
		{join(env, env.Home, ".cursor", "hooks.json"), "sessionStart", "cursor", func(v map[string]any) bool { return ownedCommand(env, stringValue(v["command"])) }},
		{join(env, env.Home, ".copilot", "hooks", "sessionStart.json"), "sessionStart", "copilot", func(v map[string]any) bool { return ownedCommand(env, stringValue(v["bash"])) }},
	}
	for _, typ := range types {
		text, ok := readText(env, typ.path)
		if !ok {
			continue
		}
		data, err := parseObject(typ.path, text)
		if err != nil {
			return nil, err
		}
		hooks, ok := data["hooks"].(map[string]any)
		if !ok {
			continue
		}
		raw, ok := hooks[typ.event].([]any)
		if !ok {
			continue
		}
		kept := make([]any, 0, len(raw))
		changed := false
		for _, item := range raw {
			obj, ok := item.(map[string]any)
			if ok && typ.match(obj) {
				changed = true
				continue
			}
			kept = append(kept, item)
		}
		if changed {
			hooks[typ.event] = kept
			add, _ := jsonWrite(typ.path, data, typ.label)
			actions = append(actions, add...)
		}
	}
	return actions, nil
}

func planPathRemove(env Environment, prefix string) []Action {
	rc := resolvedPath(env, ShellRC(env))
	existing, ok := readText(env, rc)
	if !ok {
		return nil
	}
	line := RCLine(env.Shell, prefix)
	kept := []string{}
	changed := false
	lines := strings.Split(existing, "\n")
	for i := 0; i < len(lines); i++ {
		s := lines[i]
		if strings.TrimSpace(s) == pathMarker && i+1 < len(lines) && strings.TrimSpace(lines[i+1]) == line {
			changed = true
			i++
			continue
		}
		kept = append(kept, s)
	}
	if !changed {
		return nil
	}
	text := strings.TrimRight(strings.Join(kept, "\n"), "\n") + "\n"
	return []Action{{Kind: "write", Path: rc, Text: text, Label: "PATH"}}
}

func mergeNestedHook(data map[string]any, event string, entry map[string]any, match func(map[string]any) bool) (bool, error) {
	hooks, ok := data["hooks"].(map[string]any)
	if !ok {
		if data["hooks"] != nil {
			return false, fmt.Errorf("hooks must be an object")
		}
		hooks = map[string]any{}
		data["hooks"] = hooks
	}
	raw, ok := hooks[event].([]any)
	if !ok {
		if hooks[event] != nil {
			return false, fmt.Errorf("hooks.%s must be an array", event)
		}
		raw = []any{}
	}
	out := make([]any, 0, len(raw)+1)
	found, changed := false, false
	for _, item := range raw {
		obj, ok := item.(map[string]any)
		if !ok {
			return false, fmt.Errorf("hooks.%s entries must be objects", event)
		}
		if match(obj) {
			found = true
			if !jsonEqual(obj, entry) {
				changed = true
			}
			out = append(out, entry)
		} else {
			out = append(out, item)
		}
	}
	if !found {
		out = append(out, entry)
		changed = true
	}
	if changed {
		hooks[event] = out
	}
	return changed, nil
}

func hookCommand(env Environment, harness string) string {
	return runPrefix(env, join(env, env.Checkout, "bin", "docket")) + " context --for " + harness
}
func runPrefix(env Environment, executable string) string {
	if env.GOOS == "windows" {
		return quoteCommand(env.Python) + " " + quoteCommand(executable)
	}
	return shellQuote(executable)
}
func posixRun(env Environment, executable string) string {
	return shellQuote(executable)
}
func quoteCommand(s string) string { return `"` + strings.ReplaceAll(s, `"`, `\"`) + `"` }
func shellQuote(s string) string   { return "'" + strings.ReplaceAll(s, "'", "'\\''") + "'" }
func ownedCommand(env Environment, command string) bool {
	return strings.Contains(command, join(env, env.Checkout, "bin", "docket"))
}

func openCodeSource(env Environment) string {
	py, _ := json.Marshal(env.Python)
	docket, _ := json.Marshal(join(env, env.Checkout, "bin", "docket"))
	return fmt.Sprintf("import { execFileSync } from \"node:child_process\"\n\nconst PYTHON = %s\nconst DOCKET = %s\n\nexport const Docket = async () => {\n  return {\n    \"experimental.chat.system.transform\": async (input, output) => {\n      try {\n        const ledger = execFileSync(PYTHON, [DOCKET, \"context\"], {\n          encoding: \"utf8\",\n          env: { ...process.env, DOCKET_AUTHOR: \"opencode\" },\n        })\n        if (ledger.trim()) output.system.push(ledger)\n      } catch {\n        return\n      }\n    },\n  }\n}\n", py, docket)
}

func cursorRuleText() string {
	return "---\nalwaysApply: true\n---\n\nSee docket's skill for when and how to record a decision.\n"
}

func codexReceipt(env Environment) string {
	raw, _ := json.MarshalIndent(map[string]string{"checkout": env.Checkout}, "", "  ")
	return string(raw) + "\n"
}

func ownedWindowsShim(text, docket string) bool {
	const prefix = "@echo off\r\n\""
	const suffix = "\" %*\r\n"
	if !strings.HasPrefix(text, prefix) || !strings.HasSuffix(text, suffix) {
		return false
	}
	body := strings.TrimSuffix(strings.TrimPrefix(text, prefix), suffix)
	parts := strings.SplitN(body, "\" \"", 2)
	return len(parts) == 2 && parts[0] != "" && parts[1] == docket
}

func ownedOpenCode(env Environment, text string) bool {
	normalize := func(source string) string {
		lines := strings.Split(source, "\n")
		for i, line := range lines {
			if strings.HasPrefix(line, "const PYTHON = ") {
				lines[i] = "const PYTHON = <installer-python>"
			}
		}
		return strings.Join(lines, "\n")
	}
	return normalize(text) == normalize(openCodeSource(env))
}

func loadObject(env Environment, p string) (map[string]any, error) {
	text, ok := readText(env, p)
	if !ok {
		return map[string]any{}, nil
	}
	return parseObject(p, text)
}
func parseObject(p, text string) (map[string]any, error) {
	var data map[string]any
	if err := json.Unmarshal([]byte(text), &data); err != nil {
		return nil, fmt.Errorf("%s: malformed JSON: %w", p, err)
	}
	if data == nil {
		return nil, fmt.Errorf("%s: JSON root must be an object", p)
	}
	return data, nil
}
func jsonWrite(p string, data map[string]any, label string) ([]Action, error) {
	raw, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return nil, err
	}
	return []Action{{Kind: "write", Path: p, Text: string(raw) + "\n", Label: label}}, nil
}
func jsonEqual(a, b any) bool {
	x, _ := json.Marshal(a)
	y, _ := json.Marshal(b)
	return string(x) == string(y)
}
func stringValue(v any) string { s, _ := v.(string); return s }

func ShellRC(env Environment) string {
	switch base(env.Shell) {
	case "zsh":
		return join(env, env.Home, ".zshrc")
	case "bash":
		return join(env, env.Home, ".bashrc")
	case "fish":
		return join(env, env.Home, ".config", "fish", "config.fish")
	default:
		return join(env, env.Home, ".profile")
	}
}
func RCLine(shell, directory string) string {
	if base(shell) == "fish" {
		return "fish_add_path " + shellQuote(directory)
	}
	return "export PATH=" + shellQuote(directory) + ":\"$PATH\""
}
func PathContains(entries []string, directory, goos string) bool {
	want := strings.TrimRight(directory, "/\\")
	for _, e := range entries {
		got := strings.TrimRight(e, "/\\")
		if goos == "windows" {
			if strings.EqualFold(got, want) {
				return true
			}
		} else if got == want {
			return true
		}
	}
	return false
}
func DescribeAction(a Action) string {
	switch a.Kind {
	case "write":
		return "write  " + a.Path
	case "link":
		return "link   " + a.Path + " -> " + a.Source
	case "remove":
		return "remove " + a.Path
	case "command":
		return "run    " + strings.Join(a.Args, " ")
	case "path-add":
		if a.Source != "" {
			return "add    " + a.Path + " to PATH (receipt " + a.Source + ")"
		}
		return "add    " + a.Path + " to PATH"
	case "path-remove":
		return "remove " + a.Path + " from PATH"
	case "checkout":
		return "checkout " + a.Path + " (replace local files; keep .docket)"
	case "checkout-update":
		return "update checkout " + a.Path + " (fast-forward; keep local files)"
	case "viewer":
		return "prepare graph viewer " + a.Path + " (build from source or fetch a verified release)"
	default:
		return a.Kind + " " + a.Path
	}
}

func readText(env Environment, p string) (string, bool) {
	if env.ReadFile == nil {
		return "", false
	}
	b, err := env.ReadFile(p)
	return string(b), err == nil
}
func sameFile(env Environment, p, text string) bool {
	got, ok := readText(env, p)
	return ok && got == text
}
func readlink(env Environment, p string) (string, error) {
	if env.Readlink == nil {
		return "", fmt.Errorf("readlink unavailable")
	}
	return env.Readlink(p)
}
func resolvedPath(env Environment, p string) string {
	target, err := readlink(env, p)
	if err != nil {
		return p
	}
	if env.GOOS != "windows" && !path.IsAbs(target) {
		return path.Clean(path.Join(path.Dir(p), target))
	}
	return cleanPath(env, target)
}
func exists(env Environment, p string) bool { return env.Exists != nil && env.Exists(p) }
func commandPresent(env Environment, name string) bool {
	if env.LookPath != nil {
		if _, err := env.LookPath(name); err == nil {
			return true
		}
	}
	names := []string{name}
	if env.GOOS == "windows" {
		names = []string{name, name + ".exe", name + ".cmd"}
	}
	for _, dir := range env.Path {
		for _, n := range names {
			if exists(env, join(env, dir, n)) {
				return true
			}
		}
	}
	return false
}
func cleanPath(env Environment, p string) string {
	p = strings.TrimRight(p, "/\\")
	if env.GOOS == "windows" {
		return strings.ToLower(strings.ReplaceAll(p, "/", `\`))
	}
	return path.Clean(p)
}
func base(p string) string {
	p = strings.TrimRight(p, "/\\")
	if i := strings.LastIndexAny(p, "/\\"); i >= 0 {
		return p[i+1:]
	}
	return p
}
func join(env Environment, parts ...string) string {
	sep := "/"
	if env.GOOS == "windows" {
		sep = `\`
	}
	out := ""
	for _, part := range parts {
		if part == "" {
			continue
		}
		if out == "" {
			out = strings.TrimRight(part, "/\\")
		} else {
			out += sep + strings.Trim(part, "/\\")
		}
	}
	return out
}
