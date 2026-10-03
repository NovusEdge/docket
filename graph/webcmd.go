package main

import (
	"bufio"
	"bytes"
	"io"
	"os/exec"
	"strings"
	"time"

	tea "charm.land/bubbletea/v2"
)

// webStartTimeout is a var so tests can shorten it.
var webStartTimeout = 10 * time.Second

// webProc is the running `docket graph --web` server. Quitting the viewer
// stops it; a crash or kill of the viewer orphans it, which is acceptable
// because the server is read-only and the next `w` or Ctrl-C ends it.
type webProc struct{ cmd *exec.Cmd }

func (p *webProc) stop() {
	if p != nil && p.cmd != nil && p.cmd.Process != nil {
		_ = p.cmd.Process.Kill()
		_ = p.cmd.Wait()
	}
}

type webStartedMsg struct {
	proc *webProc
	url  string
	err  string
}

// startWeb is a var so tests replace it and spawn nothing. The child gets no
// stdin and both output streams are captured, so it never writes to the
// viewer's terminal; stdout is read for the URL line, then drained.
var startWeb = func(argv []string) tea.Cmd {
	return func() tea.Msg {
		cmd := exec.Command(argv[0], argv[1:]...)
		// A grandchild holding stderr open would otherwise block Wait.
		cmd.WaitDelay = time.Second
		out, err := cmd.StdoutPipe()
		if err != nil {
			return webStartedMsg{err: err.Error()}
		}
		var stderr bytes.Buffer
		cmd.Stderr = &stderr
		if err := cmd.Start(); err != nil {
			return webStartedMsg{err: err.Error()}
		}
		type result struct {
			line string
			err  error
		}
		done := make(chan result, 1)
		go func() {
			line, err := bufio.NewReader(out).ReadString('\n')
			done <- result{line, err}
		}()
		select {
		case r := <-done:
			if r.err != nil {
				_ = cmd.Wait()
				return webStartedMsg{err: lastLine(stderr.String(), "web view exited before printing its URL")}
			}
			go func() { _, _ = io.Copy(io.Discard, out) }()
			return webStartedMsg{proc: &webProc{cmd: cmd}, url: strings.TrimSpace(r.line)}
		case <-time.After(webStartTimeout):
			_ = cmd.Process.Kill()
			_ = cmd.Wait()
			return webStartedMsg{err: "web view did not start within " + webStartTimeout.String()}
		}
	}
}

func webArgv(base []string, query string) []string {
	argv := append([]string(nil), base...)
	if strings.TrimSpace(query) != "" {
		argv = append(argv, "--where", query)
	}
	return argv
}
