package main

import (
	"encoding/json"
	"errors"
	"flag"
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

const (
	repositoryURL = "https://github.com/Dijo-404/Proj_Setu.git"
	defaultBranch = "main"
)

var validBranch = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._/-]*$`)

type installerOptions struct {
	installDir string
	branch     string
	skipStart  bool
	skipCaddy  bool
	elevated   bool
}

type githubRelease struct {
	Assets []struct {
		Name               string `json:"name"`
		BrowserDownloadURL string `json:"browser_download_url"`
	} `json:"assets"`
}

func main() {
	options, err := parseOptions(os.Args[1:])
	if err != nil {
		fail(err)
	}

	if runtime.GOOS != "windows" {
		fail(errors.New("SetuoraInstaller.exe can only run on Windows"))
	}

	if !isAdministrator() {
		if options.elevated {
			fail(errors.New("administrator access is required to install Setuora"))
		}
		if err := relaunchElevated(options); err != nil {
			fail(fmt.Errorf("the elevated installer did not complete: %w", err))
		}
		return
	}

	if err := runInstaller(options); err != nil {
		fail(err)
	}
}

func parseOptions(arguments []string) (installerOptions, error) {
	options := installerOptions{}
	flags := flag.NewFlagSet("SetuoraInstaller", flag.ContinueOnError)
	flags.SetOutput(os.Stdout)
	flags.StringVar(&options.installDir, "install-dir", defaultInstallDirectory(), "Setuora installation directory")
	flags.StringVar(&options.branch, "branch", defaultBranch, "Git branch to install")
	flags.BoolVar(&options.skipStart, "skip-start", false, "do not start Setuora after setup")
	flags.BoolVar(&options.skipCaddy, "skip-caddy", false, "skip LAN HTTPS/Caddy setup")
	flags.BoolVar(&options.elevated, "elevated", false, "internal UAC flag")
	if err := flags.Parse(arguments); err != nil {
		return options, err
	}
	if flags.NArg() != 0 {
		return options, fmt.Errorf("unexpected argument: %s", flags.Arg(0))
	}

	options.installDir = strings.TrimSpace(options.installDir)
	options.branch = strings.TrimSpace(options.branch)
	if options.installDir == "" {
		return options, errors.New("the installation directory cannot be empty")
	}
	if !validBranch.MatchString(options.branch) || strings.Contains(options.branch, "..") {
		return options, fmt.Errorf("invalid Git branch name: %q", options.branch)
	}

	absoluteDir, err := filepath.Abs(options.installDir)
	if err != nil {
		return options, fmt.Errorf("resolve installation directory: %w", err)
	}
	options.installDir = filepath.Clean(absoluteDir)
	return options, nil
}

func defaultInstallDirectory() string {
	if executable, err := os.Executable(); err == nil {
		executableDir := filepath.Dir(executable)
		if fileExists(filepath.Join(executableDir, "setup.bat")) && fileExists(filepath.Join(executableDir, ".git")) {
			return executableDir
		}
	}
	if systemDrive := strings.TrimSpace(os.Getenv("SystemDrive")); systemDrive != "" {
		return filepath.Join(systemDrive+string(os.PathSeparator), "Setuora")
	}
	return `C:\Setuora`
}

func runInstaller(options installerOptions) error {
	fmt.Println("Setuora QR Tally Bridge Installer")
	fmt.Println("=================================")
	fmt.Printf("Installation folder: %s\n\n", options.installDir)

	gitPath, err := ensureGit()
	if err != nil {
		return err
	}

	if err := synchronizeRepository(gitPath, options.installDir, options.branch); err != nil {
		return err
	}
	if !fileExists(filepath.Join(options.installDir, "setup.bat")) {
		return fmt.Errorf("the downloaded project does not contain setup.bat: %s", options.installDir)
	}

	fmt.Println("\n== Complete Application Setup ==")
	if err := runSetup(options); err != nil {
		return fmt.Errorf("Setuora setup failed: %w", err)
	}
	fmt.Println("\nSetuora installation completed successfully.")
	return nil
}

func ensureGit() (string, error) {
	if gitPath := findGit(); gitPath != "" {
		fmt.Printf("Found Git: %s\n", gitPath)
		return gitPath, nil
	}

	fmt.Println("\n== Install Git for Windows ==")
	wingetPath := findExecutable("winget.exe", "winget")
	if wingetPath != "" {
		fmt.Println("Git was not found. Installing it with WinGet...")
		err := runVisible(
			wingetPath,
			"install", "--id", "Git.Git", "-e", "--source", "winget",
			"--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity",
		)
		if gitPath := findGit(); gitPath != "" {
			return gitPath, nil
		}
		if err != nil {
			fmt.Println("WinGet could not complete the Git installation; trying the official Git for Windows installer...")
		} else {
			fmt.Println("WinGet completed, but Git was not found; trying the official Git for Windows installer...")
		}
	}

	if err := installGitFromOfficialRelease(); err != nil {
		return "", fmt.Errorf("install Git for Windows: %w", err)
	}
	if gitPath := findGit(); gitPath != "" {
		return gitPath, nil
	}
	return "", errors.New("Git installation completed, but git.exe could not be located; restart Windows and run the installer again")
}

func findGit() string {
	if gitPath := findExecutable("git.exe", "git"); gitPath != "" {
		return gitPath
	}

	candidates := []string{
		filepath.Join(os.Getenv("ProgramFiles"), "Git", "cmd", "git.exe"),
		filepath.Join(os.Getenv("ProgramFiles(x86)"), "Git", "cmd", "git.exe"),
		filepath.Join(os.Getenv("LOCALAPPDATA"), "Programs", "Git", "cmd", "git.exe"),
		filepath.Join(os.Getenv("LOCALAPPDATA"), "Microsoft", "WinGet", "Links", "git.exe"),
	}
	for _, candidate := range candidates {
		if fileExists(candidate) {
			return candidate
		}
	}
	return ""
}

func findExecutable(names ...string) string {
	for _, name := range names {
		if path, err := exec.LookPath(name); err == nil {
			return path
		}
	}
	return ""
}

func installGitFromOfficialRelease() error {
	client := &http.Client{Timeout: 30 * time.Minute}
	request, err := http.NewRequest(http.MethodGet, "https://api.github.com/repos/git-for-windows/git/releases/latest", nil)
	if err != nil {
		return err
	}
	request.Header.Set("Accept", "application/vnd.github+json")
	request.Header.Set("User-Agent", "SetuoraInstaller")

	response, err := client.Do(request)
	if err != nil {
		return fmt.Errorf("query official Git release: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("query official Git release: HTTP %s", response.Status)
	}

	var release githubRelease
	if err := json.NewDecoder(response.Body).Decode(&release); err != nil {
		return fmt.Errorf("read official Git release: %w", err)
	}

	downloadURL := ""
	assetName := ""
	for _, asset := range release.Assets {
		name := strings.ToLower(asset.Name)
		if strings.HasPrefix(name, "git-") && strings.HasSuffix(name, "-64-bit.exe") && !strings.Contains(name, "portable") {
			downloadURL = asset.BrowserDownloadURL
			assetName = asset.Name
			break
		}
	}
	if downloadURL == "" {
		return errors.New("the official Git release did not contain a 64-bit Windows installer")
	}

	fmt.Printf("Downloading %s...\n", assetName)
	installerResponse, err := client.Get(downloadURL)
	if err != nil {
		return fmt.Errorf("download Git installer: %w", err)
	}
	defer installerResponse.Body.Close()
	if installerResponse.StatusCode != http.StatusOK {
		return fmt.Errorf("download Git installer: HTTP %s", installerResponse.Status)
	}

	temporaryFile, err := os.CreateTemp("", "Setuora-Git-*.exe")
	if err != nil {
		return err
	}
	temporaryPath := temporaryFile.Name()
	defer os.Remove(temporaryPath)
	if _, err := io.Copy(temporaryFile, installerResponse.Body); err != nil {
		temporaryFile.Close()
		return fmt.Errorf("save Git installer: %w", err)
	}
	if err := temporaryFile.Close(); err != nil {
		return err
	}

	if err := verifyAuthenticodeSignature(temporaryPath); err != nil {
		return fmt.Errorf("verify the downloaded Git installer: %w", err)
	}
	fmt.Println("Running the official Git for Windows installer...")
	return runVisible(temporaryPath, "/VERYSILENT", "/NORESTART", "/NOCANCEL", "/SP-")
}

func verifyAuthenticodeSignature(path string) error {
	script := "$signature=Get-AuthenticodeSignature -LiteralPath " + powershellQuote(path) +
		"; if ($signature.Status -ne 'Valid') { Write-Error ('Invalid Authenticode signature: ' + $signature.Status); exit 1 }"
	return runVisible("powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script)
}

func synchronizeRepository(gitPath, installDir, branch string) error {
	fmt.Println("\n== Download or Update Setuora ==")
	gitDirectory := filepath.Join(installDir, ".git")
	if !fileExists(gitDirectory) {
		if exists, empty, err := directoryState(installDir); err != nil {
			return err
		} else if exists && !empty {
			return fmt.Errorf("%s exists but is not a Setuora Git checkout; choose an empty --install-dir", installDir)
		}
		if err := os.MkdirAll(filepath.Dir(installDir), 0o755); err != nil {
			return fmt.Errorf("create installation parent folder: %w", err)
		}
		fmt.Printf("Cloning %s branch %s...\n", repositoryURL, branch)
		if err := runVisible(gitPath, "clone", "--branch", branch, "--single-branch", repositoryURL, installDir); err != nil {
			return fmt.Errorf("clone Setuora: %w", err)
		}
		return nil
	}

	remote, err := gitOutput(gitPath, installDir, "remote", "get-url", "origin")
	if err != nil {
		return fmt.Errorf("read the Setuora Git remote: %w", err)
	}
	if !isSetuoraRemote(remote) {
		return fmt.Errorf("the existing origin remote is %q, expected %s", strings.TrimSpace(remote), repositoryURL)
	}

	currentBranch, err := gitOutput(gitPath, installDir, "branch", "--show-current")
	if err != nil {
		return fmt.Errorf("read the current Git branch: %w", err)
	}
	if strings.TrimSpace(currentBranch) != branch {
		return fmt.Errorf("the existing checkout is on branch %q, expected %q", strings.TrimSpace(currentBranch), branch)
	}

	fmt.Printf("Updating branch %s from GitHub...\n", branch)
	if err := runGitVisible(gitPath, installDir, "fetch", "--no-tags", "origin", branch); err != nil {
		return fmt.Errorf("download the latest Setuora files: %w", err)
	}
	if err := runGitVisible(gitPath, installDir, "merge", "--ff-only", "FETCH_HEAD"); err != nil {
		fmt.Println("A fast-forward update was not possible; matching the published branch exactly.")
		if err := runGitVisible(gitPath, installDir, "reset", "--hard", "FETCH_HEAD"); err != nil {
			return fmt.Errorf("synchronize Setuora files: %w", err)
		}
	}
	return nil
}

func runSetup(options installerOptions) error {
	arguments := []string{"/d", "/c", "setup.bat"}
	if options.skipStart {
		arguments = append(arguments, "-SkipStart")
	}
	if options.skipCaddy {
		arguments = append(arguments, "-SkipCaddy")
	}
	command := exec.Command("cmd.exe", arguments...)
	command.Dir = options.installDir
	command.Stdin = os.Stdin
	command.Stdout = os.Stdout
	command.Stderr = os.Stderr
	return command.Run()
}

func runGitVisible(gitPath, installDir string, arguments ...string) error {
	return runVisible(gitPath, append([]string{"-c", "safe.directory=" + installDir, "-C", installDir}, arguments...)...)
}

func gitOutput(gitPath, installDir string, arguments ...string) (string, error) {
	commandArguments := append([]string{"-c", "safe.directory=" + installDir, "-C", installDir}, arguments...)
	output, err := exec.Command(gitPath, commandArguments...).CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("%w: %s", err, strings.TrimSpace(string(output)))
	}
	return string(output), nil
}

func runVisible(name string, arguments ...string) error {
	command := exec.Command(name, arguments...)
	command.Stdin = os.Stdin
	command.Stdout = os.Stdout
	command.Stderr = os.Stderr
	return command.Run()
}

func isAdministrator() bool {
	command := exec.Command(
		"powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
		`$identity=[Security.Principal.WindowsIdentity]::GetCurrent(); $principal=New-Object Security.Principal.WindowsPrincipal($identity); if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { exit 0 } else { exit 1 }`,
	)
	return command.Run() == nil
}

func relaunchElevated(options installerOptions) error {
	executable, err := os.Executable()
	if err != nil {
		return err
	}
	arguments := []string{"--elevated", "--install-dir", options.installDir, "--branch", options.branch}
	if options.skipStart {
		arguments = append(arguments, "--skip-start")
	}
	if options.skipCaddy {
		arguments = append(arguments, "--skip-caddy")
	}
	quotedArguments := make([]string, 0, len(arguments))
	for _, argument := range arguments {
		quotedArguments = append(quotedArguments, windowsQuoteArgument(argument))
	}
	commandLine := strings.Join(quotedArguments, " ")
	script := "$process=Start-Process -FilePath " + powershellQuote(executable) +
		" -Verb RunAs -Wait -PassThru -ArgumentList " + powershellQuote(commandLine) +
		"; exit $process.ExitCode"
	command := exec.Command("powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script)
	command.Stdin = os.Stdin
	command.Stdout = os.Stdout
	command.Stderr = os.Stderr
	return command.Run()
}

func isSetuoraRemote(remote string) bool {
	normalized := strings.ToLower(strings.TrimSpace(remote))
	normalized = strings.TrimSuffix(normalized, "/")
	normalized = strings.TrimSuffix(normalized, ".git")
	switch {
	case strings.HasPrefix(normalized, "https://"):
		normalized = strings.TrimPrefix(normalized, "https://")
	case strings.HasPrefix(normalized, "ssh://git@github.com/"):
		normalized = "github.com/" + strings.TrimPrefix(normalized, "ssh://git@github.com/")
	case strings.HasPrefix(normalized, "git@github.com:"):
		normalized = "github.com/" + strings.TrimPrefix(normalized, "git@github.com:")
	}
	return normalized == "github.com/dijo-404/proj_setu"
}

func powershellQuote(value string) string {
	return "'" + strings.ReplaceAll(value, "'", "''") + "'"
}

func windowsQuoteArgument(argument string) string {
	if argument != "" && !strings.ContainsAny(argument, " \t\n\v\"") {
		return argument
	}

	var result strings.Builder
	result.WriteByte('"')
	backslashes := 0
	for _, character := range argument {
		switch character {
		case '\\':
			backslashes++
		case '"':
			result.WriteString(strings.Repeat("\\", backslashes*2+1))
			result.WriteRune(character)
			backslashes = 0
		default:
			result.WriteString(strings.Repeat("\\", backslashes))
			result.WriteRune(character)
			backslashes = 0
		}
	}
	result.WriteString(strings.Repeat("\\", backslashes*2))
	result.WriteByte('"')
	return result.String()
}

func directoryState(path string) (exists, empty bool, err error) {
	directory, err := os.Open(path)
	if errors.Is(err, os.ErrNotExist) {
		return false, true, nil
	}
	if err != nil {
		return false, false, err
	}
	defer directory.Close()
	if info, err := directory.Stat(); err != nil {
		return true, false, err
	} else if !info.IsDir() {
		return true, false, fmt.Errorf("%s is not a directory", path)
	}
	_, err = directory.Readdirnames(1)
	if errors.Is(err, io.EOF) {
		return true, true, nil
	}
	if err != nil {
		return true, false, err
	}
	return true, false, nil
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

func fail(err error) {
	fmt.Fprintf(os.Stderr, "\nInstallation failed: %v\n", err)
	fmt.Fprintln(os.Stderr, "Your existing Setuora data and .env were not removed.")
	fmt.Print("Press Enter to close...")
	_, _ = fmt.Fscanln(os.Stdin)
	os.Exit(1)
}
