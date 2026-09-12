package main

import (
	"context"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

func NormalizePath(path, home, cwd string) (string, error) {
	if strings.ContainsRune(path, 0) || strings.ContainsAny(path, "\r\n") {
		return "", errors.New("paths cannot contain NUL or newline characters")
	}
	if path == "~" {
		path = home
	} else if strings.HasPrefix(path, "~/") || strings.HasPrefix(path, "~\\") {
		path = filepath.Join(home, path[2:])
	} else if strings.HasPrefix(path, "~") {
		return "", errors.New("use ~ or an absolute path, not ~username")
	}
	if path == "" {
		return "", errors.New("path cannot be empty")
	}
	if !filepath.IsAbs(path) {
		path = filepath.Join(cwd, path)
	}
	return filepath.Clean(path), nil
}

func ExecutePlan(ctx context.Context, plan Plan, notify func(Progress)) error {
	for i, action := range plan.Actions {
		if err := ctx.Err(); err != nil {
			return err
		}
		err := executeAction(ctx, action)
		if notify != nil {
			notify(Progress{Index: i, Action: action, Err: err})
		}
		if err != nil {
			return fmt.Errorf("%s: %w", action.Label, err)
		}
	}
	return nil
}

func executeAction(ctx context.Context, a Action) error {
	switch a.Kind {
	case "write":
		return atomicWrite(a.Path, []byte(a.Text))
	case "link":
		if err := os.MkdirAll(filepath.Dir(a.Path), 0755); err != nil {
			return err
		}
		dir, err := os.MkdirTemp(filepath.Dir(a.Path), ".docket-link-")
		if err != nil {
			return err
		}
		defer os.RemoveAll(dir)
		link := filepath.Join(dir, "link")
		if err := os.Symlink(a.Source, link); err != nil {
			return fmt.Errorf("create link (Windows may require Developer Mode): %w", err)
		}
		return os.Rename(link, a.Path)
	case "remove":
		err := os.Remove(a.Path)
		if errors.Is(err, os.ErrNotExist) {
			return nil
		}
		return err
	case "command":
		if len(a.Args) == 0 {
			return errors.New("empty command")
		}
		out, err := exec.CommandContext(ctx, a.Args[0], a.Args[1:]...).CombinedOutput()
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if err != nil {
			return fmt.Errorf("%s: %w\n%s", a.Args[0], err, strings.TrimSpace(string(out)))
		}
		return nil
	case "path-add":
		return applyPathAdd(a, updateUserPath)
	case "path-remove":
		_, err := updateUserPath(a.Path, true)
		return err
	case "checkout":
		return cloneCheckout(ctx, a)
	case "checkout-update":
		return updateCheckout(ctx, a)
	case "viewer":
		return executeViewerAction(ctx, a)
	default:
		return fmt.Errorf("unknown action %q", a.Kind)
	}
}

func updateCheckout(ctx context.Context, a Action) error {
	info, err := os.Stat(a.Path)
	if err != nil {
		return fmt.Errorf("update checkout: %w", err)
	}
	if !info.IsDir() {
		return fmt.Errorf("update checkout: %s is not a directory", a.Path)
	}
	if _, err := runCheckoutGit(ctx, a.Path, "rev-parse", "--is-inside-work-tree"); err != nil {
		return fmt.Errorf("update checkout: %w", err)
	}
	remote := a.Source
	if remote == "" {
		remote = "origin"
	}
	fetchArgs := []string{"fetch", remote}
	if len(a.Args) >= 2 && a.Args[0] == "--tag" {
		fetchArgs = append(fetchArgs, a.Args[1])
	}
	if _, err := runCheckoutGit(ctx, a.Path, fetchArgs...); err != nil {
		return fmt.Errorf("update checkout: fetch: %w", err)
	}
	if _, err := runCheckoutGit(ctx, a.Path, "merge", "--ff-only", "FETCH_HEAD"); err != nil {
		return fmt.Errorf("update checkout: fast-forward: %w", err)
	}
	return nil
}

func runCheckoutGit(ctx context.Context, checkout string, args ...string) ([]byte, error) {
	cmd := exec.CommandContext(ctx, "git", append([]string{"-C", checkout}, args...)...)
	output, err := cmd.CombinedOutput()
	if ctx.Err() != nil {
		return output, ctx.Err()
	}
	if err != nil {
		return output, fmt.Errorf("git %s: %w\n%s", strings.Join(args, " "), err, strings.TrimSpace(string(output)))
	}
	return output, nil
}

func applyPathAdd(a Action, update func(string, bool) (bool, error)) error {
	if a.Source == "" {
		return errors.New("PATH addition has no ownership receipt")
	}
	changed, err := update(a.Path, false)
	if err != nil || !changed {
		return err
	}
	if err := atomicWrite(a.Source, []byte(a.Text)); err != nil {
		if _, rollback := update(a.Path, true); rollback != nil {
			return fmt.Errorf("record PATH ownership: %v; rollback: %w", err, rollback)
		}
		return fmt.Errorf("record PATH ownership: %w", err)
	}
	return nil
}

func atomicWrite(path string, data []byte) error {
	mode := fs.FileMode(0644)
	if info, err := os.Lstat(path); err == nil {
		if !info.Mode().IsRegular() {
			return fmt.Errorf("refusing to replace non-regular file %s", path)
		}
		mode = info.Mode().Perm()
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	f, err := os.CreateTemp(filepath.Dir(path), ".docket-write-")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	if _, err = f.Write(data); err != nil {
		f.Close()
		return err
	}
	if err = f.Chmod(mode); err != nil {
		f.Close()
		return err
	}
	if err = f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err = f.Close(); err != nil {
		return err
	}
	return os.Rename(f.Name(), path)
}

func validateCheckoutTarget(path string) error {
	info, err := os.Lstat(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("%s is not a Docket checkout directory", path)
	}
	entries, err := os.ReadDir(path)
	if err != nil {
		return err
	}
	if len(entries) == 0 {
		return nil
	}
	if info, err := os.Stat(filepath.Join(path, "bin", "docket")); err != nil || !info.Mode().IsRegular() {
		return fmt.Errorf("%s is not a Docket checkout; choose an empty directory", path)
	}
	remote, err := exec.Command("git", "-C", path, "remote", "get-url", "origin").Output()
	if err != nil {
		return fmt.Errorf("%s is not a Docket checkout with a known origin", path)
	}
	origin := strings.TrimSuffix(strings.ToLower(strings.TrimSpace(string(remote))), ".git")
	if origin != "https://github.com/novusedge/docket" && origin != "git@github.com:novusedge/docket" {
		return fmt.Errorf("%s is not a Docket checkout from NovusEdge/docket; use --checkout to install a local source tree", path)
	}
	return nil
}

func cloneCheckout(ctx context.Context, a Action) error {
	if err := validateCheckoutTarget(a.Path); err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(a.Path), 0755); err != nil {
		return err
	}
	// Staging beside the destination keeps the final rename on one filesystem.
	dir, err := os.MkdirTemp(filepath.Dir(a.Path), ".docket-stage-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(dir)
	staged := filepath.Join(dir, "checkout")
	args := []string{"clone", "--depth", "1"}
	args = append(args, a.Args...)
	args = append(args, "--", a.Source, staged)
	out, err := exec.CommandContext(ctx, "git", args...).CombinedOutput()
	if ctx.Err() != nil {
		return ctx.Err()
	}
	if err != nil {
		return fmt.Errorf("git clone: %w\n%s", err, strings.TrimSpace(string(out)))
	}
	if info, err := os.Stat(filepath.Join(staged, "bin", "docket")); err != nil || !info.Mode().IsRegular() {
		return errors.New("downloaded checkout has no bin/docket")
	}
	return swapCheckout(staged, a.Path)
}

func swapCheckout(staged, dest string) error {
	if info, err := os.Stat(staged); err != nil {
		return err
	} else if !info.IsDir() {
		return errors.New("staged checkout is not a directory")
	}
	if _, err := os.Lstat(dest); errors.Is(err, os.ErrNotExist) {
		return os.Rename(staged, dest)
	} else if err != nil {
		return err
	}
	// Project ledgers are user data, even when stored inside the managed checkout.
	ledger := filepath.Join(dest, ".docket")
	if _, err := os.Lstat(ledger); err == nil {
		if _, err := os.Lstat(filepath.Join(staged, ".docket")); !errors.Is(err, os.ErrNotExist) {
			return errors.New("new checkout contains .docket; refusing to overwrite the existing ledger")
		}
		if err := copyTree(ledger, filepath.Join(staged, ".docket")); err != nil {
			return fmt.Errorf("preserve ledger: %w", err)
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}
	backup, err := os.MkdirTemp(filepath.Dir(dest), ".docket-old-")
	if err != nil {
		return err
	}
	if err := os.Remove(backup); err != nil {
		return err
	}
	if err := os.Rename(dest, backup); err != nil {
		return err
	}
	if err := os.Rename(staged, dest); err != nil {
		if restore := os.Rename(backup, dest); restore != nil {
			return fmt.Errorf("replace: %v; restore: %v; original retained at %s", err, restore, backup)
		}
		return err
	}
	if err := os.RemoveAll(backup); err != nil {
		return fmt.Errorf("updated checkout, but old copy remains at %s: %w", backup, err)
	}
	return nil
}

func copyTree(src, dst string) error {
	return filepath.WalkDir(src, func(path string, d fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		rel, err := filepath.Rel(src, path)
		if err != nil {
			return err
		}
		target := filepath.Join(dst, rel)
		info, err := d.Info()
		if err != nil {
			return err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			link, err := os.Readlink(path)
			if err != nil {
				return err
			}
			return os.Symlink(link, target)
		}
		if d.IsDir() {
			return os.MkdirAll(target, info.Mode().Perm())
		}
		if !info.Mode().IsRegular() {
			return fmt.Errorf("unsupported file in ledger: %s", path)
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		return os.WriteFile(target, data, info.Mode().Perm())
	})
}
