package main

import (
	"errors"
	"fmt"
	"strings"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows/registry"
)

func updateUserPath(directory string, remove bool) (bool, error) {
	key, err := registry.OpenKey(registry.CURRENT_USER, "Environment", registry.QUERY_VALUE|registry.SET_VALUE)
	if err != nil {
		return false, err
	}
	defer key.Close()
	value, kind, err := key.GetStringValue("Path")
	if errors.Is(err, registry.ErrNotExist) {
		if remove {
			return false, nil
		}
		value = ""
		kind = registry.EXPAND_SZ
	} else if err != nil {
		return false, err
	}
	if kind != registry.SZ && kind != registry.EXPAND_SZ {
		return false, fmt.Errorf("unsupported PATH registry type %d", kind)
	}
	parts := strings.Split(value, ";")
	out := make([]string, 0, len(parts)+1)
	found := false
	for _, part := range parts {
		matches := strings.EqualFold(strings.TrimRight(part, "/\\"), strings.TrimRight(directory, "/\\"))
		if matches {
			found = true
			if remove {
				continue
			}
		}
		out = append(out, part)
	}
	if remove && !found || !remove && found {
		return false, nil
	}
	if !remove {
		if len(out) == 1 && out[0] == "" {
			out = nil
		}
		out = append(out, directory)
	}
	updated := strings.Join(out, ";")
	if kind == registry.EXPAND_SZ {
		err = key.SetExpandStringValue("Path", updated)
	} else {
		err = key.SetStringValue("Path", updated)
	}
	if err != nil {
		return false, err
	}
	env, err := syscall.UTF16PtrFromString("Environment")
	if err != nil {
		return true, err
	}
	proc := syscall.NewLazyDLL("user32.dll").NewProc("SendMessageTimeoutW")
	var result uintptr
	_, _, _ = proc.Call(0xffff, 0x001a, 0, uintptr(unsafe.Pointer(env)), 0x0002, 5000, uintptr(unsafe.Pointer(&result)))
	return true, nil
}
