package main

import (
	"context"
	"fmt"
	"image/color"
	"io"
	"os"
	"sort"
	"strings"

	"charm.land/bubbles/v2/help"
	"charm.land/bubbles/v2/key"
	"charm.land/bubbles/v2/list"
	"charm.land/bubbles/v2/spinner"
	"charm.land/bubbles/v2/textinput"
	"charm.land/bubbles/v2/viewport"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"
)

const (
	defaultTUIWidth  = 80
	defaultTUIHeight = 24
)

type tuiPhase int

const (
	phaseChecks tuiPhase = iota
	phasePrefix
	phaseCheckout
	phaseHarnesses
	phasePath
	phaseReview
	phaseApplying
	phaseDone
)

var tuiKeys = struct {
	Enter, Toggle, Yes, No, Quit, Cancel, Move, Scroll, Apply key.Binding
}{
	Enter:  key.NewBinding(key.WithKeys("enter"), key.WithHelp("enter", "next")),
	Toggle: key.NewBinding(key.WithKeys("space"), key.WithHelp("space", "pick")),
	Yes:    key.NewBinding(key.WithKeys("y", "Y"), key.WithHelp("y", "yes")),
	No:     key.NewBinding(key.WithKeys("n", "N"), key.WithHelp("n", "no")),
	Quit:   key.NewBinding(key.WithKeys("q"), key.WithHelp("q", "cancel")),
	Cancel: key.NewBinding(key.WithKeys("ctrl+c", "esc"), key.WithHelp("esc", "cancel")),
	Move:   key.NewBinding(key.WithKeys("up", "down"), key.WithHelp("up/down", "move")),
	Scroll: key.NewBinding(key.WithKeys("up", "down"), key.WithHelp("up/down", "scroll")),
	Apply:  key.NewBinding(key.WithKeys("enter", "y"), key.WithHelp("enter", "apply")),
}

type harnessItem struct {
	harness  Harness
	selected bool
}

func (h harnessItem) FilterValue() string { return h.harness.Name }
func (h harnessItem) Title() string       { return h.harness.Name }
func (h harnessItem) Description() string {
	if h.harness.Detected && h.harness.Detail != "" {
		return "detected: " + h.harness.Detail
	}
	if h.harness.Detected {
		return "detected"
	}
	if h.harness.Detail != "" {
		return h.harness.Detail
	}
	return "available"
}

type harnessDelegate struct {
	normal, selected, detail lipgloss.Style
}

func (d harnessDelegate) Height() int                         { return 2 }
func (d harnessDelegate) Spacing() int                        { return 0 }
func (d harnessDelegate) Update(tea.Msg, *list.Model) tea.Cmd { return nil }
func (d harnessDelegate) Render(w io.Writer, m list.Model, index int, raw list.Item) {
	item, ok := raw.(harnessItem)
	if !ok {
		return
	}
	mark := "[ ]"
	if item.selected {
		mark = "[x]"
	}
	style := d.normal
	if index == m.Index() {
		style = d.selected
	}
	cursor := "  "
	if index == m.Index() {
		cursor = "> "
	}
	title := ansi.Truncate(cursor+mark+" "+item.Title(), max(8, m.Width()-2), "…")
	fmt.Fprint(w, style.Render(title))
	if desc := item.Description(); desc != "" {
		fmt.Fprint(w, "\n", d.detail.Render(ansi.Truncate(desc, max(8, m.Width()-4), "…")))
	}
}

type tuiReadyMsg struct{}
type tuiProgressMsg Progress
type tuiAppliedMsg struct {
	err error
}

type tuiModel struct {
	env           Environment
	opts          Options
	executor      Executor
	phase         tuiPhase
	prefix        textinput.Model
	checkout      textinput.Model
	harnessList   list.Model
	harnesses     []Harness
	selected      map[string]bool
	plan          Plan
	progress      []Progress
	spin          spinner.Model
	help          help.Model
	view          viewport.Model
	width, height int
	dark          bool
	ctx           context.Context
	cancel        context.CancelFunc
	cancelled     bool
	err           error
	progressCh    chan tea.Msg
}

func newTUIModel(env Environment, opts Options, executor Executor) tuiModel {
	if executor == nil {
		executor = ExecutePlan
	}
	prefix := textinput.New()
	prefix.Prompt = ""
	prefix.SetValue(first(opts.Prefix, env.DefaultPrefix))
	prefix.Focus()
	checkout := textinput.New()
	checkout.Prompt = ""
	checkout.SetValue(first(opts.Dir, env.DefaultDir))
	harnesses := DetectHarnesses(env)
	items := make([]list.Item, 0, len(harnesses))
	selected := make(map[string]bool, len(harnesses))
	for _, h := range harnesses {
		items = append(items, harnessItem{harness: h, selected: h.Detected})
		selected[h.Name] = h.Detected
	}
	d := harnessDelegate{}
	l := list.New(items, d, defaultTUIWidth-4, 10)
	l.Title = "agent harnesses"
	l.SetFilteringEnabled(false)
	l.SetShowStatusBar(false)
	l.SetShowTitle(false)
	l.SetShowPagination(false)
	l.SetShowHelp(false)
	sp := spinner.New()
	sp.Spinner = spinner.Dot
	v := viewport.New(viewport.WithWidth(defaultTUIWidth-4), viewport.WithHeight(12))
	v.SoftWrap = true
	m := tuiModel{env: env, opts: opts, executor: executor, phase: phaseChecks,
		prefix: prefix, checkout: checkout, harnessList: l, harnesses: harnesses,
		selected: selected, spin: sp, help: help.New(), view: v,
		width: defaultTUIWidth, height: defaultTUIHeight, dark: true}
	m.restyle()
	return m
}

func first(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func (m tuiModel) Init() tea.Cmd {
	return tea.Batch(func() tea.Msg { return tuiReadyMsg{} }, tea.RequestBackgroundColor, m.spin.Tick)
}

func (m tuiModel) Failed() bool { return m.err != nil || m.cancelled }

func (m tuiModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tuiReadyMsg:
		m.phase = phasePrefix
		return m, nil
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
		if m.width < 20 {
			m.width = 20
		}
		if m.height < 5 {
			m.height = 5
		}
		m.resizeComponents()
		return m, nil
	case tea.BackgroundColorMsg:
		m.dark = msg.IsDark()
		m.restyle()
		return m, nil
	case spinner.TickMsg:
		if m.phase != phaseChecks && m.phase != phaseApplying {
			return m, nil
		}
		var cmd tea.Cmd
		m.spin, cmd = m.spin.Update(msg)
		return m, cmd
	case tuiAppliedMsg:
		if m.cancel != nil {
			m.cancel()
		}
		m.err = msg.err
		m.phase = phaseDone
		return m, tea.Quit
	case tuiProgressMsg:
		m.progress = append(m.progress, Progress(msg))
		return m, m.waitProgressCmd()
	case tea.KeyPressMsg:
		return m.updateKey(msg)
	}
	if m.phase == phaseReview {
		var cmd tea.Cmd
		m.view, cmd = m.view.Update(msg)
		return m, cmd
	}
	return m, nil
}

func (m tuiModel) updateKey(msg tea.KeyPressMsg) (tea.Model, tea.Cmd) {
	if key.Matches(msg, tuiKeys.Cancel) || (key.Matches(msg, tuiKeys.Quit) && m.phase != phasePrefix && m.phase != phaseCheckout) {
		if m.phase == phaseApplying {
			m.cancelled = true
			if m.cancel != nil {
				m.cancel()
			}
			return m, nil
		}
		m.cancelled = true
		m.phase = phaseDone
		return m, tea.Quit
	}
	switch m.phase {
	case phasePrefix:
		if key.Matches(msg, tuiKeys.Enter) {
			value, err := NormalizePath(m.prefix.Value(), m.env.Home, m.env.Cwd)
			if err != nil {
				m.err, m.phase = err, phaseDone
				return m, tea.Quit
			}
			m.opts.Prefix = value
			if m.opts.Uninstall {
				return m.prepareReview()
			}
			if m.opts.Checkout == "" {
				m.phase = phaseCheckout
				m.prefix.Blur()
				m.checkout.Focus()
			} else {
				m.phase = phaseHarnesses
			}
			return m, nil
		}
		var cmd tea.Cmd
		m.prefix, cmd = m.prefix.Update(msg)
		return m, cmd
	case phaseCheckout:
		if key.Matches(msg, tuiKeys.Enter) {
			value, err := NormalizePath(m.checkout.Value(), m.env.Home, m.env.Cwd)
			if err != nil {
				m.err, m.phase = err, phaseDone
				return m, tea.Quit
			}
			m.opts.Dir = value
			m.phase = phaseHarnesses
			return m, nil
		}
		var cmd tea.Cmd
		m.checkout, cmd = m.checkout.Update(msg)
		return m, cmd
	case phaseHarnesses:
		if key.Matches(msg, tuiKeys.No) {
			m.opts.Harness = []string{}
			return m.prepareReview()
		}
		if key.Matches(msg, tuiKeys.Toggle) {
			if item, ok := m.harnessList.SelectedItem().(harnessItem); ok {
				item.selected = !item.selected
				m.selected[item.harness.Name] = item.selected
				m.harnessList.SetItem(m.harnessList.Index(), item)
			}
			return m, nil
		}
		if key.Matches(msg, tuiKeys.Enter) {
			m.opts.Harness = m.selectedHarnesses()
			return m.prepareReview()
		}
		var cmd tea.Cmd
		m.harnessList, cmd = m.harnessList.Update(msg)
		return m, cmd
	case phasePath:
		if key.Matches(msg, tuiKeys.No) {
			m.plan.Actions = withoutPathAdds(m.plan.Actions)
			m.phase = phaseReview
			m.refreshReview()
			return m, nil
		}
		if key.Matches(msg, tuiKeys.Yes) || key.Matches(msg, tuiKeys.Enter) {
			m.phase = phaseReview
			m.refreshReview()
			return m, nil
		}
	case phaseReview:
		if key.Matches(msg, tuiKeys.Yes) || key.Matches(msg, tuiKeys.Enter) {
			m.phase = phaseApplying
			m.ctx, m.cancel = context.WithCancel(context.Background())
			return m, tea.Batch(m.applyCmd(), m.spin.Tick)
		}
		if key.Matches(msg, tuiKeys.No) {
			m.cancelled = true
			m.phase = phaseDone
			return m, tea.Quit
		}
		var cmd tea.Cmd
		m.view, cmd = m.view.Update(msg)
		return m, cmd
	}
	return m, nil
}

func (m tuiModel) selectedHarnesses() []string {
	selected := make([]string, 0, len(m.selected))
	for name, yes := range m.selected {
		if yes {
			selected = append(selected, name)
		}
	}
	sort.Strings(selected)
	return selected
}

func (m tuiModel) prepareReview() (tea.Model, tea.Cmd) {
	plan, err := PreparePlan(m.env, m.opts)
	if err != nil {
		m.err, m.phase = err, phaseDone
		return m, tea.Quit
	}
	m.plan = plan
	if !m.opts.Uninstall && hasPathAdd(plan.Actions) {
		m.phase = phasePath
	} else {
		m.phase = phaseReview
		m.refreshReview()
	}
	return m, nil
}

func hasPathAdd(actions []Action) bool {
	for _, action := range actions {
		if action.Kind == "path-add" || (action.Kind == "write" && action.Label == "PATH") {
			return true
		}
	}
	return false
}

func withoutPathAdds(actions []Action) []Action {
	filtered := make([]Action, 0, len(actions))
	for _, action := range actions {
		if action.Kind == "path-add" || (action.Kind == "write" && action.Label == "PATH") {
			continue
		}
		filtered = append(filtered, action)
	}
	return filtered
}

func (m *tuiModel) applyCmd() tea.Cmd {
	m.progressCh = make(chan tea.Msg, len(m.plan.Actions)+1)
	ch := m.progressCh
	go func() {
		err := m.executor(m.ctx, m.plan, func(p Progress) { ch <- tuiProgressMsg(p) })
		ch <- tuiAppliedMsg{err: err}
	}()
	return m.waitProgressCmd()
}

func (m tuiModel) waitProgressCmd() tea.Cmd {
	ch := m.progressCh
	return func() tea.Msg { return <-ch }
}

func (m *tuiModel) resizeComponents() {
	inner := max(16, m.width-4)
	m.harnessList.SetSize(inner, max(4, min(12, m.height-10)))
	m.help.SetWidth(inner)
	m.view.SetWidth(inner)
	// Header, settled choices, review title and key help occupy ten rows.
	m.view.SetHeight(max(1, m.height-10))
	m.prefix.SetWidth(inner)
	m.checkout.SetWidth(inner)
	if m.phase == phaseReview {
		m.refreshReview()
	}
}

func (m *tuiModel) restyle() {
	muted, accent, _, _ := m.palette()
	m.spin.Style = accent
	m.help.Styles.ShortKey = accent
	m.help.Styles.ShortDesc = muted
	m.help.Styles.ShortSeparator = muted
	m.help.Styles.Ellipsis = muted
	for _, input := range []*textinput.Model{&m.prefix, &m.checkout} {
		styles := input.Styles()
		styles.Focused.Prompt = accent
		styles.Focused.Text = lipgloss.NewStyle()
		styles.Blurred.Text = lipgloss.NewStyle()
		input.SetStyles(styles)
	}
	delegate := harnessDelegate{normal: lipgloss.NewStyle(), selected: accent.Bold(true), detail: muted.PaddingLeft(2)}
	m.harnessList.SetDelegate(delegate)
}

func (m *tuiModel) refreshReview() {
	lines := make([]string, 0, len(m.plan.Actions)+len(m.plan.Notes)+1)
	for i, action := range m.plan.Actions {
		lines = append(lines, fmt.Sprintf("%2d. %s", i+1, DescribeAction(action)))
	}
	for _, note := range m.plan.Notes {
		lines = append(lines, "note: "+note)
	}
	if len(lines) == 0 {
		lines = append(lines, "No changes are needed.")
	}
	m.view.SetContent(ansi.Wordwrap(strings.Join(lines, "\n"), max(10, m.width-6), " /-"))
}

func (m tuiModel) View() tea.View {
	return tea.NewView(m.render())
}

func (m tuiModel) render() string {
	width := max(16, m.width-4)
	muted, accent, good, bad := m.palette()
	heading := accent.Bold(true).Render("docket")
	scope := "scope: user"
	if m.opts.Project {
		scope = "scope: project"
	}
	checkout := first(m.opts.Checkout, m.opts.Dir, m.env.Checkout)
	if checkout != "" {
		scope += "  checkout: " + checkout
	}
	compact := m.height < 12
	blocks := []string{heading}
	if !compact {
		blocks = append(blocks, muted.Render(ansi.Truncate(scope, width, "…")), "")
	}
	if !compact && m.phase > phasePrefix {
		blocks = append(blocks, muted.Render("prefix: "+m.opts.Prefix))
	}
	if !compact && m.phase > phaseCheckout && m.opts.Checkout == "" && !m.opts.Uninstall {
		blocks = append(blocks, muted.Render("checkout: "+m.opts.Dir))
	}
	if !compact && m.phase > phaseHarnesses && !m.opts.Uninstall {
		selection := strings.Join(m.opts.Harness, ", ")
		if selection == "" {
			selection = "NONE"
		}
		blocks = append(blocks, muted.Render("harnesses: "+selection))
	}
	if len(blocks) > 3 {
		blocks = append(blocks, "")
	}
	switch m.phase {
	case phaseChecks:
		blocks = append(blocks, m.spin.View()+" checking environment", "", m.shortHelp(tuiKeys.Cancel))
	case phasePrefix:
		blocks = append(blocks, "Install command to:", m.prefix.View(), "", m.shortHelp(tuiKeys.Enter, tuiKeys.Cancel))
	case phaseCheckout:
		blocks = append(blocks, "Checkout location:", m.checkout.View(), "", m.shortHelp(tuiKeys.Enter, tuiKeys.Cancel))
	case phaseHarnesses:
		blocks = append(blocks, "Select agent harnesses (n selects none):", m.harnessView(), "", m.shortHelp(tuiKeys.Cancel, tuiKeys.Move, tuiKeys.Toggle, tuiKeys.Enter))
	case phasePath:
		blocks = append(blocks, "Add the install prefix to PATH?")
		for _, action := range m.plan.Actions {
			if action.Kind == "path-add" {
				blocks = append(blocks, "User PATH: "+action.Path)
			}
			if action.Kind == "write" && action.Label == "PATH" {
				blocks = append(blocks, action.Path, RCLine(m.env.Shell, m.opts.Prefix))
			}
		}
		blocks = append(blocks, "", m.shortHelp(tuiKeys.Yes, tuiKeys.No, tuiKeys.Cancel))
	case phaseReview:
		title := "Review all changes before uninstall"
		if !m.opts.Uninstall {
			title = "Review all changes before install"
		}
		blocks = append(blocks, title, m.view.View(), m.shortHelp(tuiKeys.Cancel, tuiKeys.Scroll, tuiKeys.Apply))
	case phaseApplying:
		blocks = append(blocks, m.spin.View()+" applying reviewed changes")
		blocks = append(blocks, m.progressLines(good, bad)...)
		blocks = append(blocks, muted.Render("ctrl+c cancels after the current action"))
	case phaseDone:
		switch {
		case m.cancelled:
			blocks = append(blocks, bad.Render("cancelled"))
			blocks = append(blocks, m.progressLines(good, bad)...)
			blocks = append(blocks, "No further changes were started.")
		case m.err != nil:
			blocks = append(blocks, bad.Render("failed: ")+m.err.Error())
			blocks = append(blocks, m.progressLines(good, bad)...)
			blocks = append(blocks, "Fix the error and run the installer again.")
		default:
			blocks = append(blocks, good.Render("done"))
			blocks = append(blocks, m.progressLines(good, bad)...)
			if m.opts.Uninstall {
				blocks = append(blocks, "Removal finished. Decision ledgers kept.")
			} else {
				blocks = append(blocks, fmt.Sprintf("%d operations completed. Run docket --version in a new shell.", len(m.progress)))
			}
		}
	}
	for i, block := range blocks {
		blocks[i] = ansi.Hardwrap(block, width, false)
	}
	content := strings.Join(blocks, "\n")
	lines := strings.Split(content, "\n")
	if len(lines) > m.height {
		// Keep identity and the active prompt/help visible in terminals too
		// short for the complete inline transcript. Review content scrolls in
		// its viewport; other phases retain their most recent bottom lines.
		top, bottom := 2, max(2, m.height-3)
		lines = append(append(append([]string{}, lines[:top]...), muted.Render("…")), lines[len(lines)-bottom:]...)
	}
	return lipgloss.NewStyle().PaddingLeft(2).Width(width).Render(strings.Join(lines, "\n"))
}

func (m tuiModel) progressLines(good, bad lipgloss.Style) []string {
	lines := make([]string, 0, len(m.progress))
	for _, progress := range m.progress {
		status := good.Render("ok")
		if progress.Err != nil {
			status = bad.Render("failed")
		}
		lines = append(lines, status+" "+DescribeAction(progress.Action))
	}
	return lines
}

func (m tuiModel) harnessView() string {
	if len(m.harnessList.Items()) == 0 {
		return "No harnesses detected. Press n to select NONE."
	}
	return m.harnessList.View()
}

func (m tuiModel) shortHelp(bindings ...key.Binding) string { return m.help.ShortHelpView(bindings) }

func (m tuiModel) palette() (muted, accent, good, bad lipgloss.Style) {
	pick := func(darkHex, lightHex string) color.Color {
		if m.dark {
			return lipgloss.Color(darkHex)
		}
		return lipgloss.Color(lightHex)
	}
	return lipgloss.NewStyle().Foreground(pick("#8B949E", "#59636E")),
		lipgloss.NewStyle().Foreground(pick("#C98A5B", "#7A3E12")),
		lipgloss.NewStyle().Foreground(pick("#7FB069", "#386A20")),
		lipgloss.NewStyle().Foreground(pick("#D16969", "#A12D2D"))
}

func RunTUI(env Environment, opts Options) int {
	model := newTUIModel(env, opts, ExecutePlan)
	final, err := tea.NewProgram(model).Run()
	if err != nil {
		fmt.Fprintln(os.Stderr, "docket:", err)
		return 1
	}
	result, ok := final.(tuiModel)
	if ok && result.cancelled {
		return 130
	}
	if !ok || result.Failed() {
		return 1
	}
	return 0
}
