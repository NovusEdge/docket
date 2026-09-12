package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func sha256Hex(data []byte) string {
	digest := sha256.Sum256(data)
	return hex.EncodeToString(digest[:])
}

func TestViewerPlanIsExplicitAndFollowsCheckout(t *testing.T) {
	env := testEnvironment(t)
	env.Checkout = filepath.Join(t.TempDir(), "docket")
	plan, err := PreparePlan(env, Options{Harness: []string{}})
	if err != nil {
		t.Fatal(err)
	}
	checkout, viewer := -1, -1
	for i, action := range plan.Actions {
		if action.Kind == "checkout" {
			checkout = i
		}
		if action.Kind == "viewer" {
			viewer = i
			if !strings.HasSuffix(action.Path, filepath.Join("graph", "docket-graph")) {
				t.Fatalf("viewer path = %q", action.Path)
			}
		}
	}
	if checkout < 0 || viewer < 0 || viewer <= checkout {
		t.Fatalf("checkout/viewer order = %d/%d, actions = %#v", checkout, viewer, plan.Actions)
	}
}

func TestViewerDownloadVerifiesChecksumBeforeAtomicReplacement(t *testing.T) {
	checkout := t.TempDir()
	target := filepath.Join(checkout, "graph", "docket-graph")
	if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(checkout, "VERSION"), []byte("1.2.3\n"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(target, []byte("old"), 0755); err != nil {
		t.Fatal(err)
	}
	payload := []byte("new viewer")
	digest := sha256Hex(payload)
	previous := viewerFetch
	defer func() { viewerFetch = previous }()
	viewerFetch = func(_ context.Context, url string) ([]byte, error) {
		switch {
		case strings.HasSuffix(url, "GRAPH-SHA256SUMS"):
			return []byte(digest + "  docket-graph-linux-amd64\n"), nil
		case strings.HasSuffix(url, "docket-graph-linux-amd64"):
			return payload, nil
		default:
			return nil, errors.New("unexpected URL: " + url)
		}
	}
	if err := acquireViewer(context.Background(), target, checkout, "linux", "amd64"); err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile(target)
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != string(payload) {
		t.Fatalf("viewer = %q", got)
	}
}

func TestViewerDownloadChecksumFailurePreservesExistingBinary(t *testing.T) {
	checkout := t.TempDir()
	target := filepath.Join(checkout, "graph", "docket-graph")
	if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(checkout, "VERSION"), []byte("1.2.3\n"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(target, []byte("keep"), 0755); err != nil {
		t.Fatal(err)
	}
	previous := viewerFetch
	defer func() { viewerFetch = previous }()
	viewerFetch = func(_ context.Context, url string) ([]byte, error) {
		if strings.HasSuffix(url, "GRAPH-SHA256SUMS") {
			return []byte(strings.Repeat("0", 64) + "  docket-graph-linux-amd64\n"), nil
		}
		return []byte("tampered"), nil
	}
	if err := acquireViewer(context.Background(), target, checkout, "linux", "amd64"); err == nil || !strings.Contains(err.Error(), "checksum mismatch") {
		t.Fatalf("error = %v", err)
	}
	got, err := os.ReadFile(target)
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != "keep" {
		t.Fatalf("existing viewer replaced after checksum failure: %q", got)
	}
}
