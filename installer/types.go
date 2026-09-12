package main

import "context"

type Options struct {
	Dir, Prefix, Checkout                          string
	Harness                                        []string // nil selects detected defaults; empty means explicitly none.
	Project, Yes, NoTTY, Uninstall, DryRun, Update bool
	Version                                        bool
}

type Environment struct {
	Home, Cwd, GOOS, Shell, Python, Checkout, DefaultDir, DefaultPrefix string
	Path                                                                []string
	LookPath                                                            func(string) (string, error)
	ReadFile                                                            func(string) ([]byte, error)
	Readlink                                                            func(string) (string, error)
	Exists                                                              func(string) bool
	CodexInstalled                                                      func() (bool, error)
}

type Harness struct {
	Name     string
	Detected bool
	Detail   string
}

// Every persistent operation appears in the reviewed plan, including commands.
type Action struct {
	Kind string // write, link, remove, command, path-add, path-remove, checkout, checkout-update, viewer
	Path, Source, Text, Label string
	Args                      []string
}

type Plan struct {
	Actions []Action
	Notes   []string
}

type Progress struct {
	Index  int
	Action Action
	Err    error
}

type Executor func(context.Context, Plan, func(Progress)) error
