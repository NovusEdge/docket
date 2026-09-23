package main

import (
	"strings"
	"unicode"

	tea "charm.land/bubbletea/v2"
)

// filterTerm is one term of a --where query. field is empty for a text term.
type filterTerm struct {
	field   string
	value   string
	negated bool
}

type filterQuery struct {
	terms []filterTerm
}

// parseFilter splits a query as docket/where.py _split and _term do, so a
// query with only text terms keeps the same rows here and in the CLI.
// tests/test_where.py SHARED_CASES and TestFilterTokenizerMatchesPython hold
// one table of cases. It never fails: field names and values are checked by
// the CLI when the query goes to the filter command.
func parseFilter(input string) filterQuery {
	var q filterQuery
	runes := []rune(input)
	n := len(runes)
	for i := 0; i < n; {
		if unicode.IsSpace(runes[i]) {
			i++
			continue
		}
		negated := runes[i] == '-' && i+1 < n && !unicode.IsSpace(runes[i+1])
		if negated {
			i++
		}
		var body []rune
		colon, quoted := -1, false
		for i < n && !unicode.IsSpace(runes[i]) {
			if runes[i] == '"' {
				quoted = true
				end := i + 1
				for end < n && runes[end] != '"' {
					end++
				}
				body = append(body, runes[i+1:end]...)
				i = end + 1
				continue
			}
			if runes[i] == ':' && colon == -1 && !quoted {
				colon = len(body)
			}
			body = append(body, runes[i])
			i++
		}
		q.terms = append(q.terms, newFilterTerm(negated, body, colon))
	}
	return q
}

func newFilterTerm(negated bool, body []rune, colon int) filterTerm {
	if colon > 0 && asciiLetters(body[:colon]) {
		return filterTerm{field: strings.ToLower(string(body[:colon])), value: string(body[colon+1:]), negated: negated}
	}
	// strings.ToLower is Go's own case folding, not Python's str.lower. They
	// disagree on İ (Turkish dotted capital I) and a word-final Σ, so the same
	// text term can match differently here than in docket/where.py.
	return filterTerm{value: strings.ToLower(string(body)), negated: negated}
}

func asciiLetters(runes []rune) bool {
	for _, r := range runes {
		if (r < 'a' || r > 'z') && (r < 'A' || r > 'Z') {
			return false
		}
	}
	return true
}

func (q filterQuery) hasFields() bool {
	for _, t := range q.terms {
		if t.field != "" {
			return true
		}
	}
	return false
}

func (q filterQuery) hasText() bool {
	for _, t := range q.terms {
		if t.field == "" {
			return true
		}
	}
	return false
}

// textMatches applies the text terms only, over the fields the CLI's text
// term reads: id, text, choice, and rationale.
func (q filterQuery) textMatches(e Entry) bool {
	fields := []string{e.ID, e.Question, e.Choice, e.Rationale}
	for _, t := range q.terms {
		if t.field != "" {
			continue
		}
		hit := false
		for _, f := range fields {
			if strings.Contains(strings.ToLower(f), t.value) {
				hit = true
				break
			}
		}
		if hit == t.negated {
			return false
		}
	}
	return true
}

// textSet is nil when the query has no text term, which shows every row.
func (m model) textSet(q filterQuery) map[string]bool {
	if !q.hasText() {
		return nil
	}
	set := make(map[string]bool)
	for _, id := range m.order {
		if q.textMatches(m.entries[id]) {
			set[id] = true
		}
	}
	return set
}

func (m *model) previewFilter() {
	id := m.selectedID()
	m.shown = m.textSet(parseFilter(m.searchInput.Value()))
	m.reselect(id)
}

// submitFilter applies the text terms at once. A query with a field term
// also runs the filter command; until it answers, the tree keeps the text
// preview. Every submission takes a new sequence number, so a slow answer to
// an earlier one cannot overwrite a later filter.
func (m model) submitFilter() (model, tea.Cmd) {
	id := m.selectedID()
	value := strings.TrimSpace(sanitize(m.searchInput.Value()))
	m.searching = false
	m.searchInput.Blur()
	m.filterSeq++
	q := parseFilter(value)
	m.query = value
	m.shown = m.textSet(q)
	m.status, m.statusErr = "", false
	var cmd tea.Cmd
	if q.hasFields() && m.filterCmd == nil {
		m.status, m.statusErr = "field filters need docket", true
	} else if q.hasFields() {
		m.pendingQuery = value
		m.status = "filtering…"
		cmd = runFilterCmd(m.filterCmd, value, m.filterSeq)
	}
	if cmd == nil {
		// No callback is in flight, so this is the state on screen: an empty
		// query, a text-only query, or a field query shown text-only for want
		// of a filter command. Esc must be able to come back to it.
		m.appliedShown, m.appliedQuery = m.shown, m.query
	}
	m.reselect(id)
	return m, cmd
}

// reselect keeps the cursor on id when the row is still visible after a
// filter change, and moves it to the first row otherwise.
func (m *model) reselect(id string) {
	m.selected = 0
	for i, row := range m.visibleRows() {
		if row.id == id {
			m.selected = i
			break
		}
	}
	m.refreshDetail()
}
