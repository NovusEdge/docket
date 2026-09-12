package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/term"
)

var version = "dev"

func main() {
	dataPath := flag.String("data", "", "normalized graph JSON path")
	plain := flag.Bool("plain", false, "render compact text instead of the interactive viewer")
	pretty := flag.Bool("pretty", false, "force colour in the interactive viewer")
	showVersion := flag.Bool("version", false, "print the viewer version")
	flag.Parse()
	if *showVersion {
		fmt.Println(version)
		return
	}
	if *dataPath == "" {
		fmt.Fprintln(os.Stderr, "docket-graph: --data PATH is required")
		os.Exit(2)
	}
	data, err := readData(*dataPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "docket-graph: %v\n", err)
		os.Exit(2)
	}
	if *plain || !isTerminal(os.Stdin) || !isTerminal(os.Stdout) {
		if err := renderPlain(os.Stdout, data); err != nil {
			fmt.Fprintf(os.Stderr, "docket-graph: %v\n", err)
			os.Exit(1)
		}
		return
	}
	program := tea.NewProgram(newModel(data, *pretty || os.Getenv("NO_COLOR") == ""))
	if _, err := program.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "docket-graph: %v\n", err)
		os.Exit(1)
	}
}

func readData(path string) (GraphData, error) {
	contents, err := os.ReadFile(path)
	if err != nil {
		return GraphData{}, err
	}
	var data GraphData
	if err := json.Unmarshal(contents, &data); err != nil {
		return GraphData{}, fmt.Errorf("invalid graph data: %w", err)
	}
	if data.Version != 2 {
		return GraphData{}, fmt.Errorf("unsupported graph data version %d; expected graph data version 2", data.Version)
	}
	seen := make(map[string]struct{}, len(data.Entries))
	for _, entry := range data.Entries {
		if entry.ID == "" {
			return GraphData{}, fmt.Errorf("graph entry has an empty id")
		}
		if _, ok := seen[entry.ID]; ok {
			return GraphData{}, fmt.Errorf("duplicate graph entry id %q", entry.ID)
		}
		seen[entry.ID] = struct{}{}
	}
	return data, nil
}

func renderPlain(w io.Writer, data GraphData) error {
	m := NewModel(data)
	for _, row := range m.rows {
		e := m.entries[row.id]
		label := strings.Repeat("  ", row.depth) + sanitize(e.ID)
		displayState := overviewState(e)
		if e.Kind != "" || displayState != "" {
			state := sanitize(stateLabel(displayState))
			if e.Kind != "" {
				label += " [" + sanitize(kindLabel(e.Kind)) + ": " + state
				if condition := decisionCondition(e); condition != "" {
					label += ", " + condition
					if condition == "blocked" && len(e.BlockedBy) > 0 {
						label += " by " + strings.Join(sanitizeList(e.BlockedBy), ", ")
					}
				}
				label += "]"
			} else {
				label += " [" + state + "]"
			}
		}
		if e.Question != "" {
			label += " " + sanitize(e.Question)
		}
		if e.RetiredBy != "" {
			label += " (retired by " + sanitize(e.RetiredBy) + ")"
		}
		if _, err := fmt.Fprintln(w, label); err != nil {
			return err
		}
	}
	return nil
}

func isTerminal(f *os.File) bool {
	if f == nil {
		return false
	}
	return term.IsTerminal(f.Fd()) && os.Getenv("TERM") != "dumb"
}
