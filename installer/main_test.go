package main

import "testing"

func TestSetuoraRemoteVariants(t *testing.T) {
	valid := []string{
		"https://github.com/Dijo-404/Proj_Setu.git",
		"https://github.com/Dijo-404/Proj_Setu/",
		"git@github.com:Dijo-404/Proj_Setu.git",
		"ssh://git@github.com/Dijo-404/Proj_Setu.git",
	}
	for _, remote := range valid {
		if !isSetuoraRemote(remote) {
			t.Errorf("expected valid Setuora remote: %s", remote)
		}
	}
	if isSetuoraRemote("https://github.com/example/Proj_Setu.git") {
		t.Fatal("accepted an unrelated repository")
	}
	if isSetuoraRemote("http://github.com/Dijo-404/Proj_Setu.git") {
		t.Fatal("accepted an insecure HTTP repository")
	}
}

func TestPowerShellQuote(t *testing.T) {
	if got, want := powershellQuote(`C:\User's Apps\Setuora.exe`), `'C:\User''s Apps\Setuora.exe'`; got != want {
		t.Fatalf("powershellQuote() = %q, want %q", got, want)
	}
}

func TestWindowsQuoteArgument(t *testing.T) {
	tests := []struct {
		input string
		want  string
	}{
		{"main", "main"},
		{"", `""`},
		{`C:\Setuora`, `C:\Setuora`},
		{`C:\Program Files\Setuora`, `"C:\Program Files\Setuora"`},
		{`C:\folder with spaces\`, `"C:\folder with spaces\\"`},
	}
	for _, test := range tests {
		if got := windowsQuoteArgument(test.input); got != test.want {
			t.Errorf("windowsQuoteArgument(%q) = %q, want %q", test.input, got, test.want)
		}
	}
}

func TestValidBranch(t *testing.T) {
	valid := []string{"main", "release/2026.07", "hotfix-1"}
	for _, branch := range valid {
		if !validBranch.MatchString(branch) {
			t.Errorf("rejected valid branch %q", branch)
		}
	}
	invalid := []string{"-main", "main branch", "main;calc.exe"}
	for _, branch := range invalid {
		if validBranch.MatchString(branch) {
			t.Errorf("accepted invalid branch %q", branch)
		}
	}
}

func TestParseOptionsSupportsUnifiedCommands(t *testing.T) {
	options, err := parseOptions([]string{"start", "--install-dir", `C:\Setuora`})
	if err != nil {
		t.Fatalf("parseOptions() returned %v", err)
	}
	if options.command != "start" {
		t.Fatalf("command = %q, want start", options.command)
	}

	options, err = parseOptions([]string{"repair", "--install-dir", `C:\Setuora`, "--port", "8123"})
	if err != nil {
		t.Fatalf("parseOptions(repair) returned %v", err)
	}
	if options.command != "repair" || options.port != 8123 {
		t.Fatalf("repair options = command %q, port %d", options.command, options.port)
	}

	options, err = parseOptions([]string{"--install-dir", `C:\Setuora`})
	if err != nil {
		t.Fatalf("parseOptions() returned %v", err)
	}
	if options.command != "setup" {
		t.Fatalf("legacy flags command = %q, want setup", options.command)
	}
}

func TestRemoveArgument(t *testing.T) {
	arguments := []string{"/d", "/c", "scripts/update.bat", "--no-pause", "-Port", "8000"}
	filtered := removeArgument(arguments, "--no-pause")
	for _, argument := range filtered {
		if argument == "--no-pause" {
			t.Fatal("removeArgument left the unwanted argument in place")
		}
	}
	if got, want := len(filtered), 5; got != want {
		t.Fatalf("len(filtered) = %d, want %d", got, want)
	}
}
