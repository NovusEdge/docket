package main

import (
	"fmt"
	"strings"
	"testing"
	"unicode"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"
)

func testData() GraphData {
	return GraphData{Version: 1, Entries: []Entry{
		{ID: "d1", State: "settled", Question: "Root", Answer: "Use the root", Sets: [][]string{{}}, Supports: []string{}},
		{ID: "d2", State: "settled", Question: "Child", Answer: "Use child", Sets: [][]string{{"d1"}}, Supports: []string{"d1"}},
		{ID: "d3", State: "ruled-out", Question: "Both", Answer: "No", Sets: [][]string{{"d1", "d2"}, {"d4"}}, Supports: []string{"d1", "d2", "d4"}, RetiredBy: "d5"},
		{ID: "d4", State: "settled", Question: "Other", Answer: "Alternative", Sets: [][]string{{}}, Supports: []string{}},
	}}
}

func TestBuildTreeShowsEveryEntryOnceAndKeepsGroups(t *testing.T) {
	m := NewModel(testData())
	if got := len(m.rows); got != len(testData().Entries) {
		t.Fatalf("rows = %d, want %d", got, len(testData().Entries))
	}
	seen := map[string]bool{}
	for _, row := range m.rows {
		if seen[row.id] {
			t.Fatalf("entry %q appears more than once", row.id)
		}
		seen[row.id] = true
	}
	detail := m.detailText(m.rows[2].id)
	for _, want := range []string{"AND", "OR", "d1", "d2", "d4", "retired by d5", "first-support tree"} {
		if !strings.Contains(detail, want) {
			t.Errorf("detail missing %q: %s", want, detail)
		}
	}
}

func TestCyclesStillProduceOneRowPerEntry(t *testing.T) {
	d := GraphData{Version: 1, Entries: []Entry{
		{ID: "a", Question: "A", Sets: [][]string{{"b"}}, Supports: []string{"b"}},
		{ID: "b", Question: "B", Sets: [][]string{{"a"}}, Supports: []string{"a"}},
		{ID: "c", Question: "C", Sets: [][]string{{"b"}}, Supports: []string{"b"}},
	}}
	m := NewModel(d)
	if len(m.rows) != 3 {
		t.Fatalf("cycle rows = %d, want 3", len(m.rows))
	}
}

func TestSelectionCollapseSearchAndDetailNavigation(t *testing.T) {
	m := NewModel(testData())
	if m.selectedID() != "d1" {
		t.Fatalf("initial selection = %q", m.selectedID())
	}
	m, _ = updateModel(m, keyMsg('j'))
	if m.selectedID() != "d2" {
		t.Fatalf("j selection = %q", m.selectedID())
	}
	m, _ = updateModel(m, keyMsg('k'))
	m, _ = updateModel(m, keyMsg(' '))
	if len(m.visibleRows()) >= len(m.rows) {
		t.Fatal("collapse did not hide descendants")
	}
	m, _ = updateModel(m, keyMsg('/'))
	m.searchInput.SetValue("other")
	m, _ = updateModel(m, keyMsg('\r'))
	if len(m.visibleRows()) != 1 || m.visibleRows()[0].id != "d4" {
		t.Fatalf("search rows = %#v", m.visibleRows())
	}
	m, _ = updateModel(m, keyMsg('\t'))
	if !m.detailFocus {
		t.Fatal("tab did not focus detail pane")
	}
	before := m.detail.YOffset()
	m, _ = updateModel(m, keyMsg('j'))
	if m.detail.YOffset() <= before && !m.detail.AtBottom() {
		t.Fatal("detail j did not scroll")
	}
}

func TestSearchAcceptsQAsInputAndSelectionStaysVisible(t *testing.T) {
	m := NewModel(testData())
	m, _ = updateModel(m, keyMsg('/'))
	m, _ = updateModel(m, tea.KeyPressMsg(tea.Key{Code: 'q', Text: "q"}))
	if !m.searching || m.searchInput.Value() != "q" {
		t.Fatalf("q was treated as quit while searching: active=%v value=%q", m.searching, m.searchInput.Value())
	}
	m, _ = updateModel(m, keyMsg('\r'))
	if m.query != "q" {
		t.Fatalf("search query = %q", m.query)
	}

	d := GraphData{Version: 1}
	for i := 0; i < 14; i++ {
		d.Entries = append(d.Entries, Entry{ID: fmt.Sprintf("d%02d", i), Question: "entry"})
	}
	m = NewModel(d)
	m, _ = updateModel(m, tea.WindowSizeMsg{Width: 80, Height: 8})
	for i := 0; i < 12; i++ {
		m, _ = updateModel(m, keyMsg('j'))
	}
	if !strings.Contains(ansi.Strip(m.View().Content), "d12") {
		t.Fatalf("selected row was scrolled out of view: %s", ansi.Strip(m.View().Content))
	}
	m = NewModel(d)
	m, _ = updateModel(m, tea.WindowSizeMsg{Width: 40, Height: 10})
	for i := 0; i < 10; i++ {
		m, _ = updateModel(m, keyMsg('j'))
	}
	if !strings.Contains(ansi.Strip(m.View().Content), "d10") {
		t.Fatalf("narrow selected row was scrolled out of view: %s", ansi.Strip(m.View().Content))
	}
}

func TestViewFitsNarrowUnicodeWidthAndSanitizesContent(t *testing.T) {
	d := GraphData{Version: 1, Entries: []Entry{{ID: "日本", State: "settled", Question: "bad\x1b[2J wide", Answer: "内容"}}}
	m := NewModel(d)
	m, _ = updateModel(m, tea.WindowSizeMsg{Width: 24, Height: 12})
	view := m.View().Content
	if strings.Contains(ansi.Strip(view), "\x1b[2J") || strings.Contains(view, "\x1b[2J") {
		t.Fatalf("control sequence leaked into view: %q", view)
	}
	for _, line := range strings.Split(view, "\n") {
		if lipgloss.Width(line) > 24 {
			t.Fatalf("line width %d exceeds 24: %q", lipgloss.Width(line), line)
		}
	}
}

func TestDetailScrollResetsOnlyWhenSelectionChanges(t *testing.T) {
	long := strings.Repeat("x", 140) + " " + strings.Repeat("word ", 80)
	m := NewModel(GraphData{Version: 1, Entries: []Entry{
		{ID: "d1", Question: "first", Answer: long},
		{ID: "d2", Question: "second", Answer: long},
	}})
	m, _ = updateModel(m, tea.WindowSizeMsg{Width: 80, Height: 8})
	m.detail.ScrollDown(4)
	m.detail.ScrollRight(24)
	if m.detail.YOffset() == 0 || m.detail.XOffset() == 0 {
		t.Fatal("fixture did not create a scroll position")
	}
	m, _ = updateModel(m, keyMsg('j'))
	if m.detailID != "d2" || m.detail.YOffset() != 0 || m.detail.XOffset() != 0 {
		t.Fatalf("selection change retained detail scroll: id=%q y=%d x=%d", m.detailID, m.detail.YOffset(), m.detail.XOffset())
	}
	m.detail.ScrollDown(1)
	m, _ = updateModel(m, tea.WindowSizeMsg{Width: 80, Height: 10})
	if m.detail.YOffset() == 0 {
		t.Fatal("resize incorrectly reset detail scroll for same selection")
	}
}

func TestSanitizeRemovesC0C1AndTerminalSequences(t *testing.T) {
	got := sanitize("ok\x1b[2J\u009b31mred\u009dtitle\u0007\u0085done")
	for _, r := range got {
		if unicode.IsControl(r) {
			t.Fatalf("control rune U+%04X survived sanitization in %q", r, got)
		}
	}
	if !strings.Contains(got, "ok") || !strings.Contains(got, "red") || !strings.Contains(got, "done") {
		t.Fatalf("sanitization discarded printable content: %q", got)
	}
}

func TestProjectedConnectorsAndLeafCollapse(t *testing.T) {
	d := GraphData{Version: 1, Entries: []Entry{
		{ID: "a", Supports: nil},
		{ID: "a1", Supports: []string{"a"}},
		{ID: "a2", Supports: []string{"a1"}},
		{ID: "b", Supports: nil},
		{ID: "b1", Supports: []string{"b"}},
		{ID: "b2", Supports: []string{"b1"}},
	}}
	view := ansi.Strip(NewModel(d).View().Content)
	var a2Line string
	for _, line := range strings.Split(view, "\n") {
		if strings.Contains(line, "a2") {
			a2Line = line
			break
		}
	}
	if !strings.Contains(a2Line, "  └─") || strings.Contains(a2Line, "│ └─") {
		t.Fatalf("rendered a2 connector = %q, want immediate-parent last-child branch", a2Line)
	}
	leaf := NewModel(GraphData{Version: 1, Entries: []Entry{{ID: "leaf"}}})
	leaf, _ = updateModel(leaf, keyMsg(' '))
	if leaf.collapsed["leaf"] || strings.Contains(ansi.Strip(leaf.View().Content), "▹") {
		t.Fatal("leaf collapse created a false collapsed marker")
	}
}

func TestRetiredEntryIsMarkedRetiredInOverview(t *testing.T) {
	m := NewModel(GraphData{Version: 1, Entries: []Entry{{ID: "d15", State: "open", Question: "historical", RetiredBy: "d16"}}})
	view := ansi.Strip(m.View().Content)
	if !strings.Contains(view, "[retired]") || strings.Contains(view, "[open]") {
		t.Fatalf("retired overview state was ambiguous: %q", view)
	}
	if !strings.Contains(m.detailText("d15"), "open") || !strings.Contains(m.detailText("d15"), "retired by d16") {
		t.Fatal("detail lost original state or retirement relationship")
	}
}

func TestTinyViewsAndFooterKeepBoundsAndEssentialControls(t *testing.T) {
	m := NewModel(testData())
	m, _ = updateModel(m, tea.WindowSizeMsg{Width: 10, Height: 3})
	view := m.View().Content
	if lipgloss.Height(view) > 3 {
		t.Fatalf("tiny view height = %d", lipgloss.Height(view))
	}
	for _, line := range strings.Split(view, "\n") {
		if lipgloss.Width(line) > 10 {
			t.Fatalf("tiny line width = %d: %q", lipgloss.Width(line), line)
		}
	}
	m, _ = updateModel(m, tea.WindowSizeMsg{Width: 60, Height: 20})
	footer := ansi.Strip(m.footer())
	for _, want := range []string{"/", "q"} {
		if !strings.Contains(footer, want) {
			t.Errorf("overview footer missing %q: %q", want, footer)
		}
	}
	m.detailFocus = true
	m, _ = updateModel(m, tea.WindowSizeMsg{Width: 80, Height: 20})
	footer = ansi.Strip(m.footer())
	for _, want := range []string{"tab", "q", "pgup", "pgdn"} {
		if !strings.Contains(footer, want) {
			t.Errorf("detail footer missing %q: %q", want, footer)
		}
	}
}

func keyMsg(k rune) tea.KeyPressMsg { return tea.KeyPressMsg(tea.Key{Code: k}) }

func updateModel(m model, msg tea.Msg) (model, tea.Cmd) {
	next, cmd := m.Update(msg)
	return next.(model), cmd
}
