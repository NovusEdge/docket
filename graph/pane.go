package main

import (
	"fmt"
	"strings"

	"charm.land/bubbles/v2/help"
	"charm.land/bubbles/v2/key"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"
)

// bodyHeightFor is the height left to the tree and the detail pane above the
// bottom pane: three pane lines from 8 rows up, one from 4 to 7. At 3 rows or
// fewer View draws its own fallback and uses no body.
func bodyHeightFor(height int) int {
	switch {
	case height >= 8:
		return height - 3
	case height >= 4:
		return height - 1
	default:
		return 0
	}
}

// overviewHeightFor is the tree's share of a stacked narrow body. The detail
// header takes one row below it, and the tree keeps at least one.
func overviewHeightFor(body int) int {
	return max(1, min(body-1, max(3, body/2)))
}

func altView(content string) tea.View {
	view := tea.NewView(content)
	view.AltScreen = true
	return view
}

func (m model) bottomPane() []string {
	if m.height < 8 {
		if m.searching {
			return []string{fitLine(m.filterLine(), m.width)}
		}
		return []string{fitLine("? help  "+m.statusLine(), m.width)}
	}
	muted := lipgloss.NewStyle().Foreground(lipgloss.Color("#7F8C98"))
	return []string{
		fitLine(m.filterLine(), m.width),
		fitLine(m.statusLine(), m.width),
		m.paint(muted, fitLine(m.footer(), m.width)),
	}
}

func (m model) filterLine() string {
	if m.searching {
		view := m.searchInput.View()
		if !m.pretty {
			view = ansi.Strip(view)
		}
		return view
	}
	if m.query == "" {
		return "filter: none"
	}
	return "filter: " + m.query
}

func (m model) statusLine() string {
	total := len(m.order)
	matched := total
	if m.shown != nil {
		matched = 0
		for _, id := range m.order {
			if m.shown[id] {
				matched++
			}
		}
	}
	parts := []string{fmt.Sprintf("%d/%d match", matched, total)}
	if visible := len(m.visibleRows()); visible < matched {
		parts = append(parts, fmt.Sprintf("%d shown", visible))
	}
	parts = append(parts, m.sortStatus())
	if m.status != "" {
		status := sanitize(m.status)
		if m.statusErr {
			status = m.paint(m.stateStyle("blocked"), status)
		}
		parts = append(parts, status)
	}
	return strings.Join(parts, " · ")
}

func (m model) footer() string {
	if m.searching {
		return "enter apply  esc cancel"
	}
	if m.width < 60 {
		return "? help  q quit"
	}
	bindings := []key.Binding{footerSearch, footerSort, footerTab, footerHelp, footerQuit}
	if m.detailFocus {
		bindings = []key.Binding{footerPageUp, footerPageDown, footerLeft, footerRight, footerTab, footerHelp, footerQuit}
	}
	m.help.SetWidth(m.width)
	result := m.help.ShortHelpView(bindings)
	if !m.pretty {
		return ansi.Strip(result)
	}
	return result
}

// helpHeading titles a column of the help overlay. Its key never reaches
// Update, which matches only the bindings in model.go.
func helpHeading(name string) key.Binding {
	return key.NewBinding(key.WithKeys(name), key.WithHelp(name, ""))
}

var helpRows = [][][]key.Binding{
	{
		{helpHeading("move"), keyUp, keyDown, keyTop, keyBottom},
		{helpHeading("fold"), keyCollapse},
		{helpHeading("sort"), keySort, keyReverse},
	},
	{
		{helpHeading("detail"), keyTab, keyPageUp, keyPageDown, keyLeft, keyRight},
		{helpHeading("filter"), keySearch, keyApply, keyCancel},
	},
}

var filterTermsHelp = []string{
	"filter terms  words AND; repeats of one field OR; is: terms AND",
	"  word          id, text, choice, or rationale contains it",
	"  -term         excludes; \"a phrase\" is always text",
	"  kind:K  state:S  is:pinned|corrected|retired|blocked",
	"  author:A  branch:B  after:YYYY-MM-DD  before:YYYY-MM-DD",
	"  scope:PATH    records whose scope governs the file PATH",
	"  scope:DIR/    records scoped to anything under DIR/",
}

func (m model) helpView() string {
	h := help.New()
	lines := []string{"keys  (any key closes this)"}
	for _, row := range helpRows {
		lines = append(lines, "")
		lines = append(lines, strings.Split(h.FullHelpView(row), "\n")...)
	}
	lines = append(lines, "")
	lines = append(lines, filterTermsHelp...)
	for i, line := range lines {
		if !m.pretty {
			line = ansi.Strip(line)
		}
		lines[i] = fitLine(line, m.width)
	}
	if len(lines) > m.height {
		lines = lines[:m.height]
	}
	return strings.Join(lines, "\n")
}
