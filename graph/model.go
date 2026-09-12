package main

import (
	"fmt"
	"os"
	"strings"
	"unicode"

	"charm.land/bubbles/v2/help"
	"charm.land/bubbles/v2/key"
	"charm.land/bubbles/v2/textinput"
	"charm.land/bubbles/v2/viewport"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"
)

type GraphData struct {
	Version int     `json:"version"`
	Entries []Entry `json:"entries"`
}

type Entry struct {
	ID            string     `json:"id"`
	Kind          string     `json:"kind"`
	State         string     `json:"state"`
	RecordedState string     `json:"recorded_state"`
	Question      string     `json:"question"`
	Answer        string     `json:"answer"`
	Choice        string     `json:"choice"`
	Cost          string     `json:"cost"`
	Sets          [][]string `json:"sets"`
	Supports      []string   `json:"supports"`
	DependsOn     []string   `json:"depends_on"`
	Answers       []string   `json:"answers"`
	Supersedes    []string   `json:"supersedes"`
	RetiredBy     string     `json:"retired_by"`
	ResolvedBy    []string   `json:"resolved_by"`
	Applicable    bool       `json:"applicable"`
	BlockedBy     []string   `json:"blocked_by"`
	DecidedBy     string     `json:"decided_by"`
	Scope         []string   `json:"scope"`
	Rationale     string     `json:"rationale"`
	Alternatives  []string   `json:"alternatives"`
	Evidence      []Evidence `json:"evidence"`
	Revisit       string     `json:"revisit"`
	Author        string     `json:"author"`
	TS            string     `json:"ts"`
	Branch        string     `json:"branch"`
	Session       string     `json:"session"`
	Pinned        bool       `json:"pinned"`
}

type Evidence struct {
	Ref       string `json:"ref"`
	CheckedAt string `json:"checked_at"`
	Commit    string `json:"commit"`
}

type graphRow struct {
	id        string
	depth     int
	last      bool
	ancestors []bool
}

// model owns the view state; graph construction is deliberately kept in
// buildRows so it can be exercised without a terminal.
type model struct {
	data              GraphData
	entries           map[string]Entry
	order             []string
	rows              []graphRow
	projectedChildren map[string]bool
	collapsed         map[string]bool
	selected          int

	searchInput   textinput.Model
	searching     bool
	query         string
	detail        viewport.Model
	detailFocus   bool
	detailID      string
	help          help.Model
	width, height int
	pretty        bool
}

var (
	keyUp          = key.NewBinding(key.WithKeys("up", "k"), key.WithHelp("↑/k", "up"))
	keyDown        = key.NewBinding(key.WithKeys("down", "j"), key.WithHelp("↓/j", "down"))
	keyCollapse    = key.NewBinding(key.WithKeys("space", "enter"), key.WithHelp("space", "collapse"))
	keySearch      = key.NewBinding(key.WithKeys("/"), key.WithHelp("/", "search"))
	keyQuit        = key.NewBinding(key.WithKeys("q", "ctrl+c"), key.WithHelp("q", "quit"))
	keyTab         = key.NewBinding(key.WithKeys("tab"), key.WithHelp("tab", "detail"))
	keyPageUp      = key.NewBinding(key.WithKeys("pgup", "ctrl+u"), key.WithHelp("pgup", "detail up"))
	keyPageDown    = key.NewBinding(key.WithKeys("pgdown", "ctrl+d"), key.WithHelp("pgdn", "detail down"))
	keyLeft        = key.NewBinding(key.WithKeys("left", "h"), key.WithHelp("h/←", "detail left"))
	keyRight       = key.NewBinding(key.WithKeys("right", "l"), key.WithHelp("l/→", "detail right"))
	footerUp       = key.NewBinding(key.WithKeys("up", "k"), key.WithHelp("↑/k", "move"))
	footerDown     = key.NewBinding(key.WithKeys("down", "j"), key.WithHelp("↓/j", "move"))
	footerCollapse = key.NewBinding(key.WithKeys("space", "enter"), key.WithHelp("space", "fold"))
	footerTab      = key.NewBinding(key.WithKeys("tab"), key.WithHelp("tab", "view"))
	footerSearch   = key.NewBinding(key.WithKeys("/"), key.WithHelp("/", "find"))
	footerQuit     = key.NewBinding(key.WithKeys("q", "ctrl+c"), key.WithHelp("q", "quit"))
	footerPageUp   = key.NewBinding(key.WithKeys("pgup", "ctrl+u"), key.WithHelp("pgup", "up"))
	footerPageDown = key.NewBinding(key.WithKeys("pgdown", "ctrl+d"), key.WithHelp("pgdn", "down"))
	footerLeft     = key.NewBinding(key.WithKeys("left", "h"), key.WithHelp("h/←", "left"))
	footerRight    = key.NewBinding(key.WithKeys("right", "l"), key.WithHelp("l/→", "right"))
)

func NewModel(data GraphData) model {
	return newModel(data, os.Getenv("NO_COLOR") == "")
}

func newModel(data GraphData, pretty bool) model {
	m := model{data: data, entries: make(map[string]Entry), collapsed: make(map[string]bool), width: 80, height: 24, pretty: pretty}
	for _, entry := range data.Entries {
		if entry.ID == "" || m.entries[entry.ID].ID != "" {
			continue
		}
		m.entries[entry.ID] = entry
		m.order = append(m.order, entry.ID)
	}
	m.rows = buildRows(m.order, m.entries)
	m.projectedChildren = projectedChildren(m.rows)
	m.searchInput = textinput.New()
	m.searchInput.Prompt = "/ "
	m.searchInput.Placeholder = "find an entry"
	m.help = help.New()
	m.detail = viewport.New(viewport.WithWidth(35), viewport.WithHeight(18))
	m.refreshDetail()
	return m
}

func buildRows(order []string, entries map[string]Entry) []graphRow {
	children := make(map[string][]string)
	parent := make(map[string]string)
	for _, id := range order {
		entry := entries[id]
		for _, support := range entry.Supports {
			if _, ok := entries[support]; ok {
				parent[id] = support
				children[support] = append(children[support], id)
				break // the overview is a first-support projection
			}
		}
	}
	// A parent chain that loops cannot have a root. Start traversal from every
	// root and then from the first remaining node, which makes cycles finite.
	var roots []string
	for _, id := range order {
		if _, ok := parent[id]; !ok {
			roots = append(roots, id)
		}
	}
	if len(roots) == 0 && len(order) > 0 {
		roots = append(roots, order[0])
	}
	rows := make([]graphRow, 0, len(order))
	seen := make(map[string]bool, len(order))
	var visit func(string, int, []bool, bool)
	visit = func(id string, depth int, ancestors []bool, last bool) {
		if seen[id] {
			return
		}
		seen[id] = true
		rows = append(rows, graphRow{id: id, depth: depth, last: last, ancestors: append([]bool(nil), ancestors...)})
		for i, child := range children[id] {
			visit(child, depth+1, append(append([]bool(nil), ancestors...), last), i == len(children[id])-1)
		}
	}
	for i, root := range roots {
		visit(root, 0, nil, i == len(roots)-1)
	}
	for _, id := range order {
		if !seen[id] {
			visit(id, 0, nil, true)
		}
	}
	return rows
}

func projectedChildren(rows []graphRow) map[string]bool {
	children := make(map[string]bool)
	stack := make([]string, 0)
	for _, row := range rows {
		if row.depth > 0 && row.depth-1 < len(stack) {
			children[stack[row.depth-1]] = true
		}
		if row.depth < len(stack) {
			stack = stack[:row.depth]
		}
		stack = append(stack, row.id)
	}
	return children
}

func (m model) selectedID() string {
	rows := m.visibleRows()
	if len(rows) == 0 {
		return ""
	}
	index := max(0, min(m.selected, len(rows)-1))
	return rows[index].id
}

func (m model) visibleRows() []graphRow {
	rows := make([]graphRow, 0, len(m.rows))
	hiddenDepth := -1
	for _, row := range m.rows {
		if hiddenDepth >= 0 {
			if row.depth > hiddenDepth {
				continue
			}
			hiddenDepth = -1
		}
		if m.query != "" && !m.matches(row.id) {
			continue
		}
		rows = append(rows, row)
		if m.collapsed[row.id] {
			hiddenDepth = row.depth
		}
	}
	return rows
}

func (m model) matches(id string) bool {
	e := m.entries[id]
	needle := strings.ToLower(m.query)
	values := []string{e.ID, e.Kind, e.State, e.RecordedState, e.Question, e.Answer, e.Choice, e.Cost, e.Rationale, e.Revisit, e.Author, e.DecidedBy, e.TS, e.Branch, e.Session, e.RetiredBy}
	values = append(values, e.Scope...)
	values = append(values, e.Alternatives...)
	values = append(values, e.Supports...)
	values = append(values, e.DependsOn...)
	values = append(values, e.Answers...)
	values = append(values, e.Supersedes...)
	values = append(values, e.ResolvedBy...)
	values = append(values, e.BlockedBy...)
	for _, set := range e.Sets {
		values = append(values, set...)
	}
	for _, evidence := range e.Evidence {
		values = append(values, evidence.Ref, evidence.CheckedAt, evidence.Commit)
	}
	for _, value := range values {
		if strings.Contains(strings.ToLower(sanitize(value)), needle) {
			return true
		}
	}
	return false
}

func (m *model) refreshDetail() {
	id := m.selectedID()
	if id == "" {
		if m.detailID != "" {
			m.detail.GotoTop()
			m.detail.SetXOffset(0)
		}
		m.detailID = ""
		m.detail.SetContent("No entries")
		return
	}
	if id != m.detailID {
		m.detail.GotoTop()
		m.detail.SetXOffset(0)
		m.detailID = id
	}
	width := max(12, m.detail.Width())
	m.detail.SetContent(wrapDetail(m.detailText(id), width))
}

func (m model) detailText(id string) string {
	e, ok := m.entries[id]
	if !ok {
		return "No entry selected"
	}
	var b strings.Builder
	effective := overviewState(e)
	kind := e.Kind
	if kind == "" {
		kind = "record"
	}
	headingStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#D7A86E"))
	labelStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("#9AA5B1"))
	idStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#F4D7A1"))
	kindStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#D7A86E"))

	fmt.Fprintf(&b, "%s  %s", m.paint(idStyle, sanitize(e.ID)), m.paint(kindStyle, sanitize(kindLabel(kind))))
	if effective != "" {
		styleState := effective
		if condition := decisionCondition(e); condition == "blocked" {
			styleState = condition
		}
		fmt.Fprintf(&b, "  %s", m.paint(m.stateStyle(styleState), sanitize(stateLabel(effective))))
		if decisionCondition(e) == "blocked" {
			fmt.Fprintf(&b, "  %s", m.paint(m.stateStyle("blocked"), "blocked"))
		}
	}

	section := func(name string) {
		if b.Len() > 0 {
			if !strings.HasSuffix(b.String(), "\n") {
				b.WriteByte('\n')
			}
			b.WriteByte('\n')
		}
		b.WriteString(m.paint(headingStyle, name))
		b.WriteByte('\n')
	}
	block := func(name, value string) {
		if value == "" {
			return
		}
		section(name)
		b.WriteString("  ")
		b.WriteString(sanitize(value))
		b.WriteByte('\n')
	}
	line := func(name, value string) {
		if value == "" {
			return
		}
		fmt.Fprintf(&b, "  %s %s\n", m.paint(labelStyle, sanitize(name)+":"), sanitize(value))
	}

	recorded := e.RecordedState
	if recorded == "" {
		recorded = e.State
	}
	block("Text", e.Question)
	if strings.EqualFold(e.Kind, "decision") {
		choice := e.Choice
		if choice == "" {
			choice = e.Answer
		}
		block("Choice", choice)
		block("Rationale", e.Rationale)
	} else if e.Rationale != "" || e.Answer != "" {
		rationale := e.Rationale
		if rationale == "" {
			rationale = e.Answer
		}
		block("Rationale", rationale)
	}
	block("Cost", e.Cost)
	block("Revisit", e.Revisit)

	section("Relationships")
	if len(e.Sets) == 0 && len(e.Supports) == 0 {
		line("Supports", "none")
	} else if len(e.Sets) > 0 {
		line("Supports", supportFormula(e.Sets))
		if len(e.Supports) > 0 && !sameSupportIDs(e.Sets, e.Supports) {
			line("Supports union", strings.Join(sanitizeList(e.Supports), ", "))
		}
	} else {
		line("Supports", strings.Join(sanitizeList(e.Supports), ", "))
	}
	line("Depends on", strings.Join(sanitizeList(e.DependsOn), ", "))
	line("Answers", strings.Join(sanitizeList(e.Answers), ", "))
	line("Resolved by", strings.Join(sanitizeList(e.ResolvedBy), ", "))
	line("Supersedes", strings.Join(sanitizeList(e.Supersedes), ", "))
	line("Blocked by", strings.Join(sanitizeList(e.BlockedBy), ", "))
	if e.RetiredBy != "" {
		line("Retired by", e.RetiredBy)
	}

	section("Metadata")
	if recorded != "" && !strings.EqualFold(recorded, effective) {
		line("Recorded", stateLabel(recorded))
	}
	if strings.EqualFold(e.Kind, "decision") {
		line("Applicable", fmt.Sprintf("%t", e.Applicable))
		if e.DecidedBy != "" {
			line("Decided by", e.DecidedBy)
		}
	}
	if len(e.Scope) > 0 {
		line("Scope", strings.Join(sanitizeList(e.Scope), ", "))
	}
	if alternatives := alternativesWithoutChoice(e.Alternatives, e.Choice, e.Answer); len(alternatives) > 0 {
		line("Alternatives", strings.Join(sanitizeList(alternatives), ", "))
	}
	if e.Author != "" {
		line("Author", e.Author)
	}
	if e.TS != "" {
		line("Timestamp", e.TS)
	}
	if e.Branch != "" {
		line("Branch", e.Branch)
	}
	if e.Session != "" {
		line("Session", e.Session)
	}
	if e.Pinned {
		line("Pinned", "true")
	}
	if len(e.Evidence) > 0 {
		section("Evidence")
		for _, evidence := range e.Evidence {
			line("Ref", evidence.Ref)
			if evidence.CheckedAt != "" {
				line("Checked at", evidence.CheckedAt)
			}
			if evidence.Commit != "" {
				line("Commit", evidence.Commit)
			}
		}
	}
	b.WriteString("\n")
	b.WriteString(m.paint(labelStyle, "Tree: first-support tree projection"))
	return strings.TrimSpace(b.String())
}

func supportFormula(sets [][]string) string {
	parts := make([]string, 0, len(sets))
	for _, set := range sets {
		if len(set) == 0 {
			parts = append(parts, "(root)")
			continue
		}
		ids := make([]string, 0, len(set))
		for _, support := range set {
			ids = append(ids, sanitize(support))
		}
		parts = append(parts, "("+strings.Join(ids, " AND ")+")")
	}
	return strings.Join(parts, " OR ")
}

func sameSupportIDs(sets [][]string, supports []string) bool {
	fromSets := make(map[string]bool)
	for _, set := range sets {
		for _, id := range set {
			fromSets[sanitize(id)] = true
		}
	}
	fromSupports := make(map[string]bool)
	for _, id := range supports {
		fromSupports[sanitize(id)] = true
	}
	if len(fromSets) != len(fromSupports) {
		return false
	}
	for id := range fromSets {
		if !fromSupports[id] {
			return false
		}
	}
	return true
}

func alternativesWithoutChoice(alternatives []string, choice, answer string) []string {
	selected := choice
	if selected == "" {
		selected = answer
	}
	result := make([]string, 0, len(alternatives))
	for _, alternative := range alternatives {
		if selected != "" && alternative == selected {
			continue
		}
		result = append(result, alternative)
	}
	return result
}

func wrapDetail(value string, width int) string {
	width = max(1, width)
	lines := make([]string, 0)
	for _, line := range strings.Split(value, "\n") {
		prefixWidth := len(line) - len(strings.TrimLeft(line, " "))
		prefix := line[:prefixWidth]
		content := line[prefixWidth:]
		available := max(1, width-ansi.StringWidth(prefix))
		parts := strings.Split(ansi.Wordwrap(content, available, " \t"), "\n")
		for _, part := range parts {
			if part == "" && prefix == "" {
				lines = append(lines, "")
				continue
			}
			lines = append(lines, prefix+part)
		}
	}
	return strings.Join(lines, "\n")
}

func (m model) Init() tea.Cmd { return nil }

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = max(1, msg.Width), max(1, msg.Height)
		m.resize()
		return m, nil
	case tea.KeyPressMsg:
		if !m.searching && key.Matches(msg, keyQuit) {
			return m, tea.Quit
		}
		if m.searching {
			if key.Matches(msg, keyTab) {
				m.searching = false
				m.searchInput.Blur()
				return m, nil
			}
			if key.Matches(msg, key.NewBinding(key.WithKeys("enter"))) {
				m.query = strings.TrimSpace(sanitize(m.searchInput.Value()))
				m.searching = false
				m.searchInput.Blur()
				m.selected = 0
				m.refreshDetail()
				return m, nil
			}
			if key.Matches(msg, key.NewBinding(key.WithKeys("esc"))) {
				m.searching = false
				m.searchInput.Blur()
				return m, nil
			}
			var cmd tea.Cmd
			m.searchInput, cmd = m.searchInput.Update(msg)
			return m, cmd
		}
		if key.Matches(msg, keySearch) {
			m.searching = true
			m.searchInput.SetValue(m.query)
			return m, m.searchInput.Focus()
		}
		if key.Matches(msg, keyTab) {
			m.detailFocus = !m.detailFocus
			return m, nil
		}
		if m.detailFocus {
			if key.Matches(msg, keyPageUp) {
				m.detail.HalfPageUp()
				return m, nil
			}
			if key.Matches(msg, keyPageDown) {
				m.detail.HalfPageDown()
				return m, nil
			}
			if key.Matches(msg, keyDown) {
				m.detail.ScrollDown(1)
				return m, nil
			}
			if key.Matches(msg, keyUp) {
				m.detail.ScrollUp(1)
				return m, nil
			}
			if key.Matches(msg, keyLeft) {
				m.detail.ScrollLeft(6)
				return m, nil
			}
			if key.Matches(msg, keyRight) {
				m.detail.ScrollRight(6)
				return m, nil
			}
			return m, nil
		}
		rows := m.visibleRows()
		if key.Matches(msg, keyUp) && len(rows) > 0 {
			m.selected = max(0, m.selected-1)
			m.refreshDetail()
			return m, nil
		}
		if key.Matches(msg, keyDown) && len(rows) > 0 {
			m.selected = min(len(rows)-1, m.selected+1)
			m.refreshDetail()
			return m, nil
		}
		if key.Matches(msg, keyCollapse) && m.selectedID() != "" {
			id := m.selectedID()
			if !m.hasChildren(id) {
				return m, nil
			}
			m.collapsed[id] = !m.collapsed[id]
			m.selected = min(m.selected, max(0, len(m.visibleRows())-1))
			m.refreshDetail()
			return m, nil
		}
	case tea.KeyReleaseMsg:
		return m, nil
	}
	return m, nil
}

func (m *model) resize() {
	m.searchInput.SetWidth(max(1, m.width-4))
	if m.width >= 70 {
		m.detail.SetWidth(max(1, m.width-m.width*46/100-3))
		m.detail.SetHeight(max(1, m.height-5))
	} else {
		m.detail.SetWidth(max(1, m.width-2))
		m.detail.SetHeight(max(1, m.height/2-2))
	}
	m.refreshDetail()
}

func (m model) View() tea.View {
	if m.width == 0 {
		m.width, m.height = 80, 24
	}
	if m.width < 1 {
		m.width = 1
	}
	if m.height < 1 {
		m.height = 1
	}
	if m.height <= 3 {
		line := "GRAPH"
		if id := m.selectedID(); id != "" {
			line += "  " + sanitize(id)
		}
		lines := []string{fitLine(line, m.width)}
		if m.height >= 2 {
			lines = append(lines, fitLine(m.footer(), m.width))
		}
		view := tea.NewView(strings.Join(lines, "\n"))
		view.AltScreen = true
		return view
	}
	leftWidth := m.width
	wide := m.width >= 70
	if wide {
		leftWidth = max(28, m.width*46/100)
	}
	bodyHeight := bodyHeightFor(m.height)
	overviewHeight := min(bodyHeight-1, max(3, bodyHeight/2))
	rows := m.visibleRows()
	titleStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#D7A86E"))
	selectedStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#F4D7A1")).Background(lipgloss.Color("#3A2F26"))
	mutedStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("#7F8C98"))
	idStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#F4D7A1"))
	kindStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("#B9A58C"))
	recordTitleStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("#E2D5C4"))
	idWidth := overviewIDWidth(rows, leftWidth)
	leftLines := []string{m.paint(titleStyle, fitLine("LEDGER GRAPH", leftWidth))}
	if m.searching {
		searchView := m.searchInput.View()
		if !m.pretty {
			searchView = ansi.Strip(searchView)
		}
		leftLines = append(leftLines, fitLine(searchView, leftWidth))
	} else if m.query != "" {
		leftLines = append(leftLines, m.paint(mutedStyle, fitLine("/ "+m.query, leftWidth)))
	}
	rowCapacity := max(1, bodyHeight-len(leftLines))
	if !wide {
		rowCapacity = max(1, overviewHeight-len(leftLines))
	}
	rowStart := 0
	if m.selected >= rowCapacity {
		rowStart = m.selected - rowCapacity + 1
	}
	rowEnd := min(len(rows), rowStart+rowCapacity)
	for i, row := range rows[rowStart:rowEnd] {
		i += rowStart
		e := m.entries[row.id]
		mark := "·"
		if m.hasChildren(row.id) {
			mark = "▾"
		}
		if m.collapsed[row.id] {
			mark = "▹"
		}
		if i == m.selected && !m.detailFocus {
			mark = "▶"
		}
		prefix := ""
		if row.depth > 0 {
			for level := 0; level < row.depth-1; level++ {
				if level+1 < len(row.ancestors) && row.ancestors[level+1] {
					prefix += "  "
				} else {
					prefix += "│ "
				}
			}
			if row.last {
				prefix += "└─ "
			} else {
				prefix += "├─ "
			}
		}
		selectedRow := i == m.selected && !m.detailFocus
		id := ansi.Truncate(sanitize(row.id), idWidth, "…")
		idCell := lipgloss.NewStyle().Width(idWidth).Render(id)
		if !selectedRow {
			idCell = m.paint(idStyle, idCell)
			prefix = m.paint(mutedStyle, prefix)
		}
		label := prefix + mark + " " + idCell
		if e.Kind != "" || overviewState(e) != "" {
			displayState := overviewState(e)
			condition := decisionCondition(e)
			styleState := displayState
			if condition == "blocked" {
				styleState = "blocked"
			}
			state := sanitize(stateLabel(displayState))
			kind := sanitize(kindLabel(e.Kind))
			if kind != "" {
				if !selectedRow {
					kind = m.paint(kindStyle, kind)
				}
				label += "  " + kind
			} else {
				label += "  "
			}
			if state != "" {
				if !selectedRow {
					state = m.paint(m.stateStyle(styleState), state)
				}
				label += "  " + state
			}
			if condition == "blocked" {
				blocked := "blocked"
				if !selectedRow {
					blocked = m.paint(m.stateStyle("blocked"), blocked)
				}
				label += "  " + blocked
			}
		}
		if e.Question != "" {
			title := sanitize(e.Question)
			if !selectedRow {
				if e.RetiredBy != "" {
					title = m.paint(mutedStyle, title)
				} else {
					title = m.paint(recordTitleStyle, title)
				}
			}
			label += "  " + title
		}
		line := fitLine(label, leftWidth)
		if selectedRow {
			line = m.paint(selectedStyle, line)
		}
		leftLines = append(leftLines, line)
	}
	if len(rows) == 0 {
		leftLines = append(leftLines, m.paint(mutedStyle, fitLine("  no matching entries", leftWidth)))
	}
	if wide {
		if len(leftLines) > bodyHeight {
			leftLines = leftLines[:bodyHeight]
		}
		for len(leftLines) < bodyHeight {
			leftLines = append(leftLines, fitLine("", leftWidth))
		}
		m.detail.SetHeight(max(1, bodyHeight-1))
		m.refreshDetail()
		detailLines := strings.Split(m.detail.View(), "\n")
		rightWidth := m.width - leftWidth - 1
		out := make([]string, bodyHeight)
		for i := range out {
			if i == 0 {
				header := "DETAIL"
				if m.detailFocus {
					header += "  [focused]"
				}
				out[i] = fitLine(leftLines[i], leftWidth) + "│" + m.paint(titleStyle, fitLine(header, rightWidth))
				continue
			}
			r := ""
			if i-1 < len(detailLines) {
				r = detailLines[i-1]
			}
			out[i] = fitLine(leftLines[i], leftWidth) + "│" + fitLine(r, rightWidth)
		}
		out = append(out, m.paint(mutedStyle, fitLine(m.footer(), m.width)))
		view := tea.NewView(strings.Join(out, "\n"))
		view.AltScreen = true
		return view
	}
	// At narrow widths the panes stack and each receives a real share of the
	// screen. The detail viewport remains scrollable with tab + j/k.
	if len(leftLines) > overviewHeight {
		leftLines = leftLines[:overviewHeight]
	}
	for len(leftLines) < overviewHeight {
		leftLines = append(leftLines, fitLine("", leftWidth))
	}
	detailHeight := max(1, bodyHeight-overviewHeight-1)
	m.detail.SetWidth(m.width)
	m.detail.SetHeight(detailHeight)
	m.refreshDetail()
	detailLines := strings.Split(m.detail.View(), "\n")
	stack := append([]string{}, leftLines...)
	header := "DETAIL"
	if m.detailFocus {
		header += "  [focused]"
	}
	stack = append(stack, m.paint(titleStyle, fitLine(header, m.width)))
	for _, line := range detailLines {
		if len(stack) >= bodyHeight {
			break
		}
		stack = append(stack, fitLine(line, m.width))
	}
	for len(stack) < bodyHeight {
		stack = append(stack, fitLine("", m.width))
	}
	stack = append(stack, m.paint(mutedStyle, fitLine(m.footer(), m.width)))
	view := tea.NewView(strings.Join(stack, "\n"))
	view.AltScreen = true
	return view
}

func bodyHeightFor(height int) int { return max(1, height-3) }

func overviewIDWidth(rows []graphRow, available int) int {
	width := 2
	for _, row := range rows {
		width = max(width, lipgloss.Width(sanitize(row.id)))
	}
	return min(16, min(width, max(2, available/3)))
}

func (m model) hasChildren(id string) bool {
	return m.projectedChildren[id]
}

func (m model) footer() string {
	if m.searching {
		return "enter apply  esc cancel"
	}
	if m.width < 70 {
		if m.detailFocus {
			return "pgup/pgdn scroll  h/l side  tab tree  q quit"
		}
		return "j/k move  space fold  tab detail  / search  q quit"
	}
	m.help.SetWidth(m.width)
	bindings := []key.Binding{footerUp, footerDown, footerCollapse, footerTab, footerSearch, footerQuit}
	if m.detailFocus {
		bindings = []key.Binding{footerPageUp, footerPageDown, footerLeft, footerRight, footerTab, footerQuit}
	}
	result := m.help.ShortHelpView(bindings)
	if !m.pretty {
		return ansi.Strip(result)
	}
	return result
}

type viewerKeyMap struct{}

func (viewerKeyMap) ShortHelp() []key.Binding {
	return []key.Binding{keyUp, keyDown, keyCollapse, keyTab, keyPageUp, keyPageDown, keySearch, keyQuit}
}

func (viewerKeyMap) FullHelp() [][]key.Binding {
	return [][]key.Binding{{keyUp, keyDown, keyCollapse, keyTab}, {keyPageUp, keyPageDown, keyLeft, keyRight}, {keySearch, keyQuit}}
}

func (m model) paint(style lipgloss.Style, value string) string {
	if !m.pretty {
		return value
	}
	return style.Render(value)
}

func (m model) stateStyle(state string) lipgloss.Style {
	switch strings.ToLower(state) {
	case "settled", "accepted", "adopted", "resolved":
		return lipgloss.NewStyle().Foreground(lipgloss.Color("#7FB069"))
	case "open", "pending", "unassessed":
		return lipgloss.NewStyle().Foreground(lipgloss.Color("#D7A86E"))
	case "blocked":
		return lipgloss.NewStyle().Foreground(lipgloss.Color("#D97858"))
	case "ruled-out", "ruled_out", "rejected", "disputed", "revoked", "retired":
		return lipgloss.NewStyle().Foreground(lipgloss.Color("#B56B6B"))
	default:
		return lipgloss.NewStyle().Foreground(lipgloss.Color("#9AA5B1"))
	}
}

func sanitize(value string) string {
	value = ansi.Strip(value)
	return strings.Map(func(r rune) rune {
		if unicode.IsControl(r) {
			return ' '
		}
		return r
	}, value)
}

func sanitizeList(values []string) []string {
	result := make([]string, len(values))
	for i, value := range values {
		result[i] = sanitize(value)
	}
	return result
}

func fitLine(value string, width int) string {
	width = max(1, width)
	truncated := ansi.Truncate(value, width, "…")
	return truncated + strings.Repeat(" ", max(0, width-ansi.StringWidth(truncated)))
}

func stateLabel(state string) string {
	switch strings.ToLower(state) {
	case "settled":
		return "settled"
	case "ruled-out", "ruled_out":
		return "ruled out"
	case "recorded":
		return "recorded"
	case "retired":
		return "retired"
	default:
		return state
	}
}

func overviewState(entry Entry) string {
	if entry.RetiredBy != "" {
		return "retired"
	}
	if entry.State != "" {
		return entry.State
	}
	return entry.RecordedState
}

func decisionCondition(entry Entry) string {
	if !strings.EqualFold(entry.Kind, "decision") || !strings.EqualFold(overviewState(entry), "adopted") {
		return ""
	}
	if entry.Applicable {
		return "applicable"
	}
	return "blocked"
}

func kindLabel(kind string) string {
	switch strings.ToLower(kind) {
	case "claim":
		return "claim"
	case "decision":
		return "decision"
	case "question":
		return "question"
	default:
		return kind
	}
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
