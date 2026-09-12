package main

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestNormalizePath(t *testing.T) {
	home, cwd := t.TempDir(), t.TempDir()
	for _, tc := range []struct{ input, want string }{
		{"~/bin", filepath.Join(home, "bin")},
		{"bin", filepath.Join(cwd, "bin")},
		{home, home},
	} {
		got, err := NormalizePath(tc.input, home, cwd)
		if err != nil || got != tc.want {
			t.Fatalf("%q: %q, %v", tc.input, got, err)
		}
	}
	if _, err := NormalizePath("~someone/bin", home, cwd); err == nil {
		t.Fatal("unsupported tilde expansion accepted")
	}
}

func TestExecutePlanWritesThenReportsAndStopsOnFailure(t *testing.T) {
	dir := t.TempDir()
	file := filepath.Join(dir, "settings.json")
	blocked := filepath.Join(dir, "directory")
	if err := os.Mkdir(blocked, 0700); err != nil {
		t.Fatal(err)
	}
	last := filepath.Join(dir, "must-not-exist")
	p := Plan{Actions: []Action{
		{Kind: "write", Path: file, Text: "original\n"},
		{Kind: "write", Path: blocked, Text: "wrong"},
		{Kind: "write", Path: last, Text: "wrong"},
	}}
	var events []Progress
	err := ExecutePlan(context.Background(), p, func(p Progress) { events = append(events, p) })
	if err == nil {
		t.Fatal("write to directory reported success")
	}
	if b, _ := os.ReadFile(file); string(b) != "original\n" {
		t.Fatalf("first action lost: %q", b)
	}
	if _, err := os.Stat(last); !errors.Is(err, os.ErrNotExist) {
		t.Fatal("continued after failed action")
	}
	if len(events) != 2 || events[0].Err != nil || events[1].Err == nil {
		t.Fatalf("progress does not report actual result: %+v", events)
	}
}

func TestCancelledPlanDoesNotWrite(t *testing.T) {
	dir := t.TempDir()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	err := ExecutePlan(ctx, Plan{Actions: []Action{{Kind: "write", Path: filepath.Join(dir, "never"), Text: "bad"}}}, nil)
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("got %v", err)
	}
	entries, _ := os.ReadDir(dir)
	if len(entries) != 0 {
		t.Fatal("cancelled plan wrote files")
	}
}

func TestAtomicWritePreservesPermissionsAndRejectsSymlinks(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "config")
	if err := os.WriteFile(target, []byte("secret"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := executeAction(context.Background(), Action{Kind: "write", Path: target, Text: "updated"}); err != nil {
		t.Fatal(err)
	}
	if runtime.GOOS == "windows" {
		return
	}
	if info, _ := os.Stat(target); info.Mode().Perm() != 0600 {
		t.Fatal("config permissions changed")
	}
	link := filepath.Join(dir, "linked")
	if err := os.Symlink(target, link); err != nil {
		t.Fatal(err)
	}
	if err := executeAction(context.Background(), Action{Kind: "write", Path: link, Text: "bad"}); err == nil {
		t.Fatal("silently replaced user config symlink")
	}
	if b, _ := os.ReadFile(target); string(b) != "updated" {
		t.Fatal("symlink target changed")
	}
}

func TestSwapCheckoutRestoresOnFailure(t *testing.T) {
	dir := t.TempDir()
	dest := filepath.Join(dir, "checkout")
	if err := os.Mkdir(dest, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dest, "marker"), []byte("keep"), 0600); err != nil {
		t.Fatal(err)
	}
	err := swapCheckout(filepath.Join(dir, "missing"), dest)
	if err == nil {
		t.Fatal("missing staged tree succeeded")
	}
	if b, _ := os.ReadFile(filepath.Join(dest, "marker")); string(b) != "keep" {
		t.Fatal("old checkout was not restored")
	}
	entries, _ := os.ReadDir(dir)
	if len(entries) != 1 {
		t.Fatalf("backup leaked: %v", entries)
	}
}

func TestSwapCheckoutPreservesProjectLedger(t *testing.T) {
	dir := t.TempDir()
	dest := filepath.Join(dir, "checkout")
	staged := filepath.Join(dir, "staged")
	if err := os.MkdirAll(filepath.Join(dest, ".docket"), 0700); err != nil {
		t.Fatal(err)
	}
	ledger := filepath.Join(dest, ".docket", "ledger.jsonl")
	if err := os.WriteFile(ledger, []byte("decision\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(staged, "bin"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(staged, "bin", "docket"), []byte("new"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := swapCheckout(staged, dest); err != nil {
		t.Fatal(err)
	}
	if b, _ := os.ReadFile(ledger); string(b) != "decision\n" {
		t.Fatal("update lost project decision ledger")
	}
	if b, _ := os.ReadFile(filepath.Join(dest, "bin", "docket")); string(b) != "new" {
		t.Fatal("new checkout missing")
	}
}

func TestCheckoutRefusesUnrelatedDirectory(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "important"), []byte("keep"), 0600); err != nil {
		t.Fatal(err)
	}
	err := executeAction(context.Background(), Action{Kind: "checkout", Path: dir, Source: "unused"})
	if err == nil || !strings.Contains(err.Error(), "not a Docket checkout") {
		t.Fatalf("unrelated directory not rejected before clone: %v", err)
	}
}

func TestCheckoutRejectsDirectoryWithOnlyDocketNamedFile(t *testing.T) {
	dir := t.TempDir()
	if err := os.Mkdir(filepath.Join(dir, "bin"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "bin", "docket"), []byte("unrelated"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := validateCheckoutTarget(dir); err == nil {
		t.Fatal("a filename alone was treated as a managed checkout")
	}
}

func TestUpdateCheckoutPreservesUntrackedFiles(t *testing.T) {
	seed, remote, checkout := gitUpdateFixture(t)
	if err := runGit(seed, "push", "origin", "HEAD"); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(checkout, "local.txt"), []byte("keep"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(seed, "tracked.txt"), []byte("updated"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := runGit(seed, "add", "tracked.txt"); err != nil {
		t.Fatal(err)
	}
	if err := runGit(seed, "commit", "-m", "update"); err != nil {
		t.Fatal(err)
	}
	if err := runGit(seed, "push", "origin", "HEAD"); err != nil {
		t.Fatal(err)
	}
	if err := executeAction(context.Background(), Action{Kind: "checkout-update", Path: checkout, Source: remote, Args: []string{"--upstream"}}); err != nil {
		t.Fatal(err)
	}
	if got, _ := os.ReadFile(filepath.Join(checkout, "tracked.txt")); string(got) != "updated" {
		t.Fatalf("tracked file was not fast-forwarded: %q", got)
	}
	if got, _ := os.ReadFile(filepath.Join(checkout, "local.txt")); string(got) != "keep" {
		t.Fatalf("untracked file was lost: %q", got)
	}
}

func TestUpdateCheckoutRefusesDirtyConflict(t *testing.T) {
	seed, remote, checkout := gitUpdateFixture(t)
	if err := os.WriteFile(filepath.Join(checkout, "tracked.txt"), []byte("local"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(seed, "tracked.txt"), []byte("remote"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := runGit(seed, "add", "tracked.txt"); err != nil {
		t.Fatal(err)
	}
	if err := runGit(seed, "commit", "-m", "conflict"); err != nil {
		t.Fatal(err)
	}
	if err := runGit(seed, "push", "origin", "HEAD"); err != nil {
		t.Fatal(err)
	}
	err := executeAction(context.Background(), Action{Kind: "checkout-update", Path: checkout, Source: remote, Args: []string{"--upstream"}})
	if err == nil || !strings.Contains(err.Error(), "fast-forward") {
		t.Fatalf("dirty conflict was accepted: %v", err)
	}
	if got, _ := os.ReadFile(filepath.Join(checkout, "tracked.txt")); string(got) != "local" {
		t.Fatalf("dirty file was changed: %q", got)
	}
}

func gitUpdateFixture(t *testing.T) (seed, remote, checkout string) {
	t.Helper()
	root := t.TempDir()
	seed, remote, checkout = filepath.Join(root, "seed"), filepath.Join(root, "remote.git"), filepath.Join(root, "checkout")
	for _, dir := range []string{seed, remote} {
		if err := os.MkdirAll(dir, 0755); err != nil {
			t.Fatal(err)
		}
	}
	if err := runGit(seed, "init"); err != nil {
		t.Fatal(err)
	}
	if err := runGit(remote, "init", "--bare"); err != nil {
		t.Fatal(err)
	}
	if err := runGit(seed, "config", "user.email", "test@example.com"); err != nil {
		t.Fatal(err)
	}
	if err := runGit(seed, "config", "user.name", "Test"); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(seed, "tracked.txt"), []byte("initial"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := runGit(seed, "add", "tracked.txt"); err != nil {
		t.Fatal(err)
	}
	if err := runGit(seed, "commit", "-m", "initial"); err != nil {
		t.Fatal(err)
	}
	if err := runGit(seed, "remote", "add", "origin", remote); err != nil {
		t.Fatal(err)
	}
	if err := runGit(seed, "push", "-u", "origin", "HEAD"); err != nil {
		t.Fatal(err)
	}
	if err := runGit(root, "clone", remote, checkout); err != nil {
		t.Fatal(err)
	}
	return seed, remote, checkout
}

func runGit(dir string, args ...string) error {
	cmd := exec.Command("git", append([]string{"-C", dir}, args...)...)
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("git %v: %w: %s", args, err, strings.TrimSpace(string(output)))
	}
	return nil
}

func TestPathAddDoesNotClaimExistingRegistryEntry(t *testing.T) {
	dir := t.TempDir()
	receipt := filepath.Join(dir, "receipt.json")
	err := applyPathAdd(Action{Path: dir, Source: receipt, Text: "owned"}, func(string, bool) (bool, error) { return false, nil })
	if err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(receipt); !os.IsNotExist(err) {
		t.Fatal("claimed ownership of a pre-existing registry entry")
	}
}

func TestPathAddRecordsOwnershipAndRollsBackReceiptFailure(t *testing.T) {
	dir := t.TempDir()
	receipt := filepath.Join(dir, "receipt.json")
	var removals int
	update := func(_ string, remove bool) (bool, error) {
		if remove {
			removals++
		}
		return true, nil
	}
	if err := applyPathAdd(Action{Path: dir, Source: receipt, Text: "owned"}, update); err != nil {
		t.Fatal(err)
	}
	if b, _ := os.ReadFile(receipt); string(b) != "owned" {
		t.Fatal("missing ownership receipt")
	}
	if err := applyPathAdd(Action{Path: dir, Source: dir, Text: "bad"}, update); err == nil {
		t.Fatal("receipt failure ignored")
	}
	if removals != 1 {
		t.Fatal("new registry entry not rolled back after receipt failure")
	}
}
