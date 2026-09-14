//go:build !windows

package main

import "errors"

func updateUserPath(_ string, _ bool) (bool, error) {
	return false, errors.New("a Windows registry PATH action was requested on a non-Windows host")
}
