//go:build !windows

package main

import "errors"

func updateUserPath(_ string, _ bool) (bool, error) {
	return false, errors.New("Windows registry PATH action on a non-Windows host")
}
