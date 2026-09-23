package main

import (
	"bytes"
	"context"
	"os/exec"
	"strings"
	"time"

	tea "charm.land/bubbletea/v2"
)

// filterTimeout is a var, not a const, so tests can shorten it instead of
// waiting out the real 10 seconds.
var filterTimeout = 10 * time.Second

// filterResultMsg carries the ids the filter command printed, or the reason
// it failed. seq ties it to the submission that started it.
type filterResultMsg struct {
	seq int
	ids []string
	err string
}

// runFilterCmd appends the query as one final argument, which the CLI's
// `_filter-ids -- QUERY` reads whole. Stdin is empty and both output streams
// are captured, so the child never writes to the viewer's terminal.
func runFilterCmd(argv []string, query string, seq int) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), filterTimeout)
		defer cancel()
		args := append(append([]string(nil), argv[1:]...), query)
		cmd := exec.CommandContext(ctx, argv[0], args...)
		var stdout, stderr bytes.Buffer
		cmd.Stdout, cmd.Stderr = &stdout, &stderr
		err := cmd.Run()
		if ctx.Err() != nil {
			return filterResultMsg{seq: seq, err: "filter timed out after " + filterTimeout.String()}
		}
		if err != nil {
			return filterResultMsg{seq: seq, err: lastLine(stderr.String(), err.Error())}
		}
		return filterResultMsg{seq: seq, ids: strings.Fields(stdout.String())}
	}
}

func lastLine(text, fallback string) string {
	lines := strings.Split(text, "\n")
	for i := len(lines) - 1; i >= 0; i-- {
		if line := strings.TrimSpace(sanitize(lines[i])); line != "" {
			return line
		}
	}
	return fallback
}

// applyFilterResult drops a result from any submission but the latest. A
// result that lands while the input is open becomes the state Esc restores.
func (m model) applyFilterResult(msg filterResultMsg) model {
	if msg.seq != m.filterSeq {
		return m
	}
	id := m.selectedID()
	if msg.err != "" {
		m.status, m.statusErr = msg.err, true
		// The applied state is the one thing still known good; restore Esc's
		// target unconditionally, and the view itself once there is no input
		// left open to preserve.
		m.prevShown, m.prevQuery = m.appliedShown, m.appliedQuery
		if !m.searching {
			m.shown, m.query = m.appliedShown, m.appliedQuery
			m.reselect(id)
		}
		return m
	}
	set := make(map[string]bool, len(msg.ids))
	for _, ident := range msg.ids {
		set[ident] = true
	}
	m.status, m.statusErr = "", false
	m.appliedShown, m.appliedQuery = set, m.pendingQuery
	if m.searching {
		m.prevShown, m.prevQuery = set, m.pendingQuery
		return m
	}
	m.shown, m.query = set, m.pendingQuery
	m.reselect(id)
	return m
}
