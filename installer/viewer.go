package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"time"
)

const viewerRepository = "NovusEdge/docket"

var viewerFetch = fetchViewerURL
var viewerLookPath = exec.LookPath

func viewerAssetName(goos, goarch string) (string, error) {
	systems := map[string]string{"linux": "linux", "darwin": "darwin", "windows": "windows"}
	architectures := map[string]string{"amd64": "amd64", "x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64"}
	system, ok := systems[strings.ToLower(goos)]
	if !ok {
		return "", fmt.Errorf("unsupported graph viewer platform %s/%s", goos, goarch)
	}
	architecture, ok := architectures[strings.ToLower(goarch)]
	if !ok {
		return "", fmt.Errorf("unsupported graph viewer platform %s/%s", goos, goarch)
	}
	suffix := ""
	if system == "windows" {
		suffix = ".exe"
	}
	return fmt.Sprintf("docket-graph-%s-%s%s", system, architecture, suffix), nil
}

func acquireViewer(ctx context.Context, target, checkout, goos, goarch string) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	source := filepath.Join(checkout, "graph")
	if _, err := viewerLookPath("go"); err == nil {
		if _, err := os.Stat(filepath.Join(source, "go.mod")); err == nil {
			return buildViewer(ctx, target, source, checkout)
		} else if !errors.Is(err, os.ErrNotExist) {
			return fmt.Errorf("inspect graph source: %w", err)
		}
	}
	return downloadViewer(ctx, target, checkout, goos, goarch)
}

func buildViewer(ctx context.Context, target, source, checkout string) error {
	if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
		return err
	}
	stage, err := os.CreateTemp(filepath.Dir(target), ".docket-graph-build-")
	if err != nil {
		return err
	}
	stagePath := stage.Name()
	if err := stage.Close(); err != nil {
		os.Remove(stagePath)
		return err
	}
	defer os.Remove(stagePath)

	args := []string{"build", "-trimpath", "-o", stagePath}
	if version, err := checkedOutVersion(checkout); err == nil {
		args = append(args, "-ldflags", "-X main.version="+version)
	}
	args = append(args, ".")
	goBinary, err := viewerLookPath("go")
	if err != nil {
		return err
	}
	cmd := exec.CommandContext(ctx, goBinary, args...)
	cmd.Dir = source
	cmd.Env = append(os.Environ(), "CGO_ENABLED=0")
	output, err := cmd.CombinedOutput()
	if ctx.Err() != nil {
		return ctx.Err()
	}
	if err != nil {
		return fmt.Errorf("build graph viewer: %w\n%s", err, strings.TrimSpace(string(output)))
	}
	payload, err := os.ReadFile(stagePath)
	if err != nil {
		return fmt.Errorf("read built graph viewer: %w", err)
	}
	return atomicInstallViewer(target, payload)
}

func downloadViewer(ctx context.Context, target, checkout, goos, goarch string) error {
	asset, err := viewerAssetName(goos, goarch)
	if err != nil {
		return err
	}
	version, err := checkedOutVersion(checkout)
	if err != nil {
		return fmt.Errorf("download graph viewer: %w", err)
	}
	base := "https://github.com/" + viewerRepository + "/releases/download/v" + version
	manifest, err := viewerFetch(ctx, base+"/GRAPH-SHA256SUMS")
	if err != nil {
		return fmt.Errorf("download graph viewer checksum manifest: %w", err)
	}
	payload, err := viewerFetch(ctx, base+"/"+asset)
	if err != nil {
		return fmt.Errorf("download graph viewer %s: %w", asset, err)
	}
	expected, err := expectedViewerChecksum(manifest, asset)
	if err != nil {
		return err
	}
	digest := sha256.Sum256(payload)
	if hex.EncodeToString(digest[:]) != expected {
		return fmt.Errorf("graph viewer checksum mismatch for %s; refusing to install it", asset)
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	if err := atomicInstallViewer(target, payload); err != nil {
		return fmt.Errorf("install graph viewer: %w", err)
	}
	return nil
}

func checkedOutVersion(checkout string) (string, error) {
	raw, err := os.ReadFile(filepath.Join(checkout, "VERSION"))
	if err != nil {
		return "", fmt.Errorf("read %s/VERSION: %w", checkout, err)
	}
	version := strings.TrimSpace(string(raw))
	version = strings.TrimPrefix(version, "v")
	if version == "" || version == "dev" || !regexp.MustCompile(`^[A-Za-z0-9._-]+$`).MatchString(version) {
		return "", fmt.Errorf("checked-out VERSION %q is not a published release", version)
	}
	return version, nil
}

func expectedViewerChecksum(manifest []byte, asset string) (string, error) {
	text := string(manifest)
	for _, line := range strings.Split(text, "\n") {
		fields := strings.Fields(line)
		if len(fields) != 2 || strings.TrimPrefix(fields[1], "*") != asset {
			continue
		}
		digest := strings.ToLower(fields[0])
		if len(digest) != sha256.Size*2 {
			return "", fmt.Errorf("GRAPH-SHA256SUMS has an invalid digest for %s", asset)
		}
		if _, err := hex.DecodeString(digest); err != nil {
			return "", fmt.Errorf("GRAPH-SHA256SUMS has an invalid digest for %s", asset)
		}
		return digest, nil
	}
	return "", fmt.Errorf("GRAPH-SHA256SUMS has no entry for %s", asset)
}

func atomicInstallViewer(target string, payload []byte) error {
	mode := os.FileMode(0755)
	if info, err := os.Lstat(target); err == nil {
		if !info.Mode().IsRegular() {
			return fmt.Errorf("refusing to replace non-regular graph viewer %s", target)
		}
		mode = info.Mode().Perm()
		if mode&0111 == 0 {
			mode = 0755
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(target), ".docket-graph-install-")
	if err != nil {
		return err
	}
	tmpPath := tmp.Name()
	defer os.Remove(tmpPath)
	if _, err := tmp.Write(payload); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Chmod(mode); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(tmpPath, target)
}

func fetchViewerURL(ctx context.Context, url string) ([]byte, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	response, err := (&http.Client{Timeout: 30 * time.Second}).Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return nil, fmt.Errorf("HTTP %s", response.Status)
	}
	return io.ReadAll(response.Body)
}

func executeViewerAction(ctx context.Context, action Action) error {
	return acquireViewer(ctx, action.Path, action.Source, runtime.GOOS, runtime.GOARCH)
}
