package main

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"charm.land/bubbles/v2/spinner"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
)

func tuiTestEnv(t *testing.T) Environment {
	t.Helper()
	home := t.TempDir()
	return Environment{
		Home: home, Cwd: home, GOOS: "linux", Shell: "/bin/sh",
		Python: "/usr/bin/python3", Checkout: home + "/src/docket",
		DefaultDir: home + "/.local/share/docket", DefaultPrefix: home + "/.local/bin",
		Exists:   func(string) bool { return false },
		ReadFile: func(string) ([]byte, error) { return nil, os.ErrNotExist },
		Readlink: func(string) (string, error) { return "", os.ErrNotExist },
	}
}

func keyMsg(code rune) tea.KeyPressMsg { return tea.KeyPressMsg(tea.Key{Code: code}) }

func updateTUICmd(t *testing.T, m tuiModel, msg tea.Msg) (tuiModel, tea.Cmd) {
	t.Helper()
	next, cmd := m.Update(msg)
	return next.(tuiModel), cmd
}

func updateTUI(t *testing.T, m tuiModel, msg tea.Msg) tuiModel {
	t.Helper()
	next, _ := updateTUICmd(t, m, msg)
	return next
}

func executionResult(t *testing.T, cmd tea.Cmd) tea.Msg {
	t.Helper()
	msg := cmd()
	if batch, ok := msg.(tea.BatchMsg); ok {
		results := make(chan tea.Msg, len(batch))
		for _, command := range batch {
			go func(c tea.Cmd) { results <- c() }(command)
		}
		for range batch {
			msg := <-results
			if _, ok := msg.(tuiAppliedMsg); ok {
				return msg
			}
		}
		t.Fatal("execution batch did not report its result")
	}
	return msg
}

func TestCancelBeforeApplyNeverCallsExecutor(t *testing.T) {
	called := false
	m := newTUIModel(tuiTestEnv(t), Options{}, func(context.Context, Plan, func(Progress)) error {
		called = true
		return nil
	})

	next, cmd := m.Update(keyMsg('q'))
	m = next.(tuiModel)
	if called {
		t.Fatal("executor ran before review was accepted")
	}
	if cmd == nil {
		t.Fatal("cancel should quit")
	}
	if !m.cancelled {
		t.Fatal("model did not record cancellation")
	}
}

func TestHarnessSelectionCanBeExplicitlyEmpty(t *testing.T) {
	env := tuiTestEnv(t)
	m := newTUIModel(env, Options{}, nil)
	m.phase = phaseHarnesses
	m.harnesses = []Harness{{Name: "codex", Detected: true}, {Name: "claude", Detected: true}}
	m.selected = map[string]bool{"codex": true, "claude": true}

	m = updateTUI(t, m, keyMsg('n'))
	if m.opts.Harness == nil || len(m.opts.Harness) != 0 {
		t.Fatalf("NONE must become an explicit empty selection, got %#v", m.opts.Harness)
	}
}

func TestDecliningPathFiltersOnlyPathAdditions(t *testing.T) {
	m := newTUIModel(tuiTestEnv(t), Options{}, nil)
	m.plan = Plan{Actions: []Action{
		{Kind: "checkout", Path: "/src"},
		{Kind: "write", Path: "/hook"},
		{Kind: "path-add", Path: "/bin", Label: "PATH"},
		{Kind: "write", Path: "/home/u/.profile", Label: "PATH"},
	}}
	m.phase = phasePath
	m = updateTUI(t, m, keyMsg('n'))
	if len(m.plan.Actions) != 2 {
		t.Fatalf("got %d actions after declining PATH", len(m.plan.Actions))
	}
	for _, action := range m.plan.Actions {
		if action.Kind == "path-add" || (action.Kind == "write" && action.Label == "PATH") {
			t.Fatalf("PATH action survived: %#v", action)
		}
	}
}

func TestUninstallReviewsPathRemovalWithoutOfferingToAddIt(t *testing.T) {
	env := tuiTestEnv(t)
	env.ReadFile = os.ReadFile
	env.Readlink = os.Readlink
	env.Exists = func(p string) bool { _, err := os.Lstat(p); return err == nil }
	content := "# added by the docket installer\nexport PATH='" + env.DefaultPrefix + "':\"$PATH\"\n"
	if err := os.WriteFile(filepath.Join(env.Home, ".profile"), []byte(content), 0600); err != nil {
		t.Fatal(err)
	}
	m := newTUIModel(env, Options{Uninstall: true}, nil)
	m.phase = phasePrefix
	m = updateTUI(t, m, keyMsg(tea.KeyEnter))
	if m.phase != phaseReview {
		t.Fatalf("uninstall entered phase %v instead of review", m.phase)
	}
	found := false
	for _, a := range m.plan.Actions {
		if a.Kind == "write" && a.Label == "PATH" {
			found = true
		}
	}
	if !found {
		t.Fatal("PATH removal disappeared")
	}
}

func TestCancelDuringApplyWaitsForExecutor(t *testing.T) {
	started := make(chan struct{})
	release := make(chan struct{})
	m := newTUIModel(tuiTestEnv(t), Options{}, func(ctx context.Context, _ Plan, _ func(Progress)) error {
		close(started)
		<-release
		return ctx.Err()
	})
	m.phase = phaseReview
	m.plan = Plan{Actions: []Action{{Kind: "write", Path: "/tmp/hook"}}}

	m, cmd := updateTUICmd(t, m, keyMsg('y'))
	if cmd == nil {
		t.Fatal("apply did not start executor")
	}
	result := make(chan tea.Msg, 1)
	go func() { result <- executionResult(t, cmd) }()
	<-started
	m, cancelCmd := updateTUICmd(t, m, tea.KeyPressMsg(tea.Key{Code: 'c', Mod: tea.ModCtrl}))
	if cancelCmd != nil {
		t.Fatal("cancelling an active apply must wait for executor result")
	}
	if m.phase != phaseApplying {
		t.Fatalf("cancel moved to phase %v before executor stopped", m.phase)
	}
	close(release)
	m = updateTUI(t, m, <-result)
	if m.phase != phaseDone || !m.cancelled {
		t.Fatalf("cancel did not finish after executor result: %#v", m)
	}
}

func TestExecutorFailureIsReportedAsFailure(t *testing.T) {
	want := errors.New("permission denied")
	m := newTUIModel(tuiTestEnv(t), Options{}, func(context.Context, Plan, func(Progress)) error { return want })
	m.phase = phaseReview
	m.plan = Plan{Actions: []Action{{Kind: "write", Path: "/protected"}}}
	m, cmd := updateTUICmd(t, m, keyMsg('y'))
	m = updateTUI(t, m, executionResult(t, cmd))
	if !m.Failed() || !errors.Is(m.err, want) {
		t.Fatalf("failure was lost: %v", m.err)
	}
}

func TestStartingExecutionSchedulesFreshSpinnerTick(t *testing.T) {
	m := newTUIModel(tuiTestEnv(t), Options{}, func(context.Context, Plan, func(Progress)) error { return nil })
	m.phase = phaseReview
	_, cmd := updateTUICmd(t, m, keyMsg('y'))
	batch, ok := cmd().(tea.BatchMsg)
	if !ok {
		t.Fatal("execution did not restart spinner alongside action processing")
	}
	found := false
	for _, command := range batch {
		if _, ok := command().(spinner.TickMsg); ok {
			found = true
		}
	}
	if !found {
		t.Fatal("execution batch has no spinner tick")
	}
}

func TestViewsFitCommonWidthsAndShortTerminalUsesViewport(t *testing.T) {
	m := newTUIModel(tuiTestEnv(t), Options{}, nil)
	m.phase = phaseReview
	for i := 0; i < 20; i++ {
		m.plan.Actions = append(m.plan.Actions, Action{Kind: "write", Path: "/a/very/long/location/that/must/wrap/configuration-file", Label: "agent hook"})
	}
	for _, size := range []struct{ w, h int }{{60, 24}, {80, 24}, {120, 24}, {60, 9}} {
		m = updateTUI(t, m, tea.WindowSizeMsg{Width: size.w, Height: size.h})
		view := m.View().Content
		for _, line := range strings.Split(view, "\n") {
			if lipgloss.Width(line) > size.w {
				t.Fatalf("line width %d exceeds terminal width %d", lipgloss.Width(line), size.w)
			}
		}
		if lipgloss.Height(view) > size.h {
			t.Fatalf("view height %d exceeds terminal height %d", lipgloss.Height(view), size.h)
		}
	}
}

func TestReviewShowsEveryPlannedActionBeforeApply(t *testing.T) {
	m := newTUIModel(tuiTestEnv(t), Options{}, nil)
	m.phase = phaseReview
	m.plan = Plan{Actions: []Action{
		{Kind: "checkout", Path: "/src/docket", Label: "clone source"},
		{Kind: "command", Label: "configure Codex", Args: []string{"codex", "plugin", "install"}},
	}}
	m.refreshReview()
	view := m.View().Content
	for _, part := range []string{"/src/docket", "codex plugin install"} {
		if !strings.Contains(view, part) {
			t.Fatalf("review omitted %q", part)
		}
	}
}

func TestEveryPhaseFitsShortTerminalAndKeepsFooterVisible(t *testing.T) {
	env := tuiTestEnv(t)
	env.DefaultPrefix = "/a/very/long/prefix/whose/value/must/not/push/the/active/help/out/of/view"
	for _, phase := range []tuiPhase{phaseChecks, phasePrefix, phaseCheckout, phaseHarnesses, phasePath, phaseReview, phaseApplying, phaseDone} {
		m := newTUIModel(env, Options{}, nil)
		m.phase = phase
		m.plan = Plan{Actions: []Action{{Kind: "write", Path: "/tmp/docket"}}}
		m.refreshReview()
		m = updateTUI(t, m, tea.WindowSizeMsg{Width: 60, Height: 10})
		view := m.View().Content
		if lipgloss.Height(view) > 10 {
			t.Fatalf("phase %v height %d exceeds terminal", phase, lipgloss.Height(view))
		}
		last := strings.TrimSpace(strings.Split(view, "\n")[lipgloss.Height(view)-1])
		if last == "" {
			t.Fatalf("phase %v lost its footer", phase)
		}
	}
}

func TestFailureAndCancellationRetainCompletedActions(t *testing.T) {
	completed := Progress{Action: Action{Kind: "write", Path: "/tmp/docket"}}
	for _, tc := range []struct {
		name      string
		cancelled bool
		err       error
	}{
		{name: "cancelled", cancelled: true},
		{name: "failed", err: errors.New("write failed")},
	} {
		t.Run(tc.name, func(t *testing.T) {
			m := newTUIModel(tuiTestEnv(t), Options{}, nil)
			m.phase, m.cancelled, m.err, m.progress = phaseDone, tc.cancelled, tc.err, []Progress{completed}
			if !strings.Contains(m.View().Content, "/tmp/docket") {
				t.Fatal("completed action disappeared from final transcript")
			}
		})
	}
}
