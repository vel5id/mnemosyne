// Package win32 provides low-level Windows API wrappers using syscall (NO CGO).
// This is the only module allowed to use unsafe operations.
package win32

import (
	"fmt"
	"sync"
	"syscall"
	"unicode/utf16"
	"unsafe"
)

// Lazy-loaded Windows DLLs
var (
	user32   = syscall.NewLazyDLL("user32.dll")
	kernel32 = syscall.NewLazyDLL("kernel32.dll")
	shell32  = syscall.NewLazyDLL("shell32.dll")
)

// Windows API functions
var (
	procGetForegroundWindow          = user32.NewProc("GetForegroundWindow")
	procGetWindowThreadProcessId     = user32.NewProc("GetWindowThreadProcessId")
	procGetWindowTextW               = user32.NewProc("GetWindowTextW")
	procGetLastInputInfo             = user32.NewProc("GetLastInputInfo")
	procGetTickCount                 = kernel32.NewProc("GetTickCount")
	procSHQueryUserNotificationState = shell32.NewProc("SHQueryUserNotificationState")
	procGetWindowRect                = user32.NewProc("GetWindowRect")
)

// LASTINPUTINFO structure for GetLastInputInfo
type LASTINPUTINFO struct {
	CBSize uint32
	DwTime uint32
}

// RECT structure for GetWindowRect
type RECT struct {
	Left   int32
	Top    int32
	Right  int32
	Bottom int32
}

// QueryUserNotificationState enum values for SHQueryUserNotificationState
const (
	QUNS_NOT_PRESENT             = 0
	QUNS_BUSY                    = 2
	QUNS_RUNNING_D3D_FULL_SCREEN = 3
	QUNS_PRESENTATION_MODE       = 4
	QUNS_ACCEPTS_NOTIFICATIONS   = 5
	QUNS_QUIET_TIME              = 6
	QUNS_APP                     = 7
)

// TextBufferPool manages reusable buffers for window text to minimize allocations
type TextBufferPool struct {
	pool sync.Pool
}

// NewTextBufferPool creates a new pool of text buffers
func NewTextBufferPool() *TextBufferPool {
	return &TextBufferPool{
		pool: sync.Pool{
			New: func() interface{} {
				// Allocate buffer for 512 UTF-16 characters (1024 bytes)
				// This should cover most window titles
				buf := make([]uint16, 512)
				return buf
			},
		},
	}
}

// Get retrieves a buffer from the pool
func (p *TextBufferPool) Get() []uint16 {
	return p.pool.Get().([]uint16)
}

// Put returns a buffer to the pool
func (p *TextBufferPool) Put(buf []uint16) {
	p.pool.Put(buf)
}

// Global text buffer pool for window titles
var textBufferPool = NewTextBufferPool()

// GetForegroundWindow retrieves the handle to the foreground window.
// Returns 0 if no foreground window exists (e.g., workstation locked).
func GetForegroundWindow() (syscall.Handle, error) {
	ret, _, err := procGetForegroundWindow.Call()
	if ret == 0 {
		return 0, fmt.Errorf("no foreground window: %w", err)
	}
	return syscall.Handle(ret), nil
}

// GetWindowThreadProcessId retrieves the identifier of the thread
// that created the specified window and, optionally, the identifier
// of the process that created the window.
func GetWindowThreadProcessId(hwnd syscall.Handle) (uint32, uint32, error) {
	var pid uint32
	ret, _, err := procGetWindowThreadProcessId.Call(
		uintptr(hwnd),
		uintptr(unsafe.Pointer(&pid)),
	)
	if ret == 0 {
		return 0, 0, fmt.Errorf("failed to get thread/process ID: %w", err)
	}
	return uint32(ret), pid, nil
}

// GetWindowText retrieves the text of the specified window's title bar.
// Uses a reusable buffer from the pool to minimize allocations.
func GetWindowText(hwnd syscall.Handle) (string, error) {
	buf := textBufferPool.Get()
	defer textBufferPool.Put(buf)

	ret, _, err := procGetWindowTextW.Call(
		uintptr(hwnd),
		uintptr(unsafe.Pointer(&buf[0])),
		uintptr(len(buf)),
	)
	if ret == 0 {
		return "", fmt.Errorf("failed to get window text: %w", err)
	}

	// Convert UTF-16 to Go string
	// Find null terminator
	length := int(ret)
	if length > len(buf) {
		length = len(buf)
	}

	// Convert to string
	str := syscall.UTF16ToString(buf[:length])
	return str, nil
}

// GetWindowRect retrieves the dimensions of the bounding rectangle of the specified window.
func GetWindowRect(hwnd syscall.Handle) (*RECT, error) {
	var rect RECT
	ret, _, err := procGetWindowRect.Call(
		uintptr(hwnd),
		uintptr(unsafe.Pointer(&rect)),
	)
	if ret == 0 {
		return nil, fmt.Errorf("failed to get window rect: %w", err)
	}
	return &rect, nil
}

// GetLastInputInfo retrieves the time of the last input event.
// Returns the tick count of the last input event.
func GetLastInputInfo() (uint32, error) {
	var info LASTINPUTINFO
	info.CBSize = uint32(unsafe.Sizeof(info))

	ret, _, err := procGetLastInputInfo.Call(
		uintptr(unsafe.Pointer(&info)),
	)
	if ret == 0 {
		return 0, fmt.Errorf("failed to get last input info: %w", err)
	}

	return info.DwTime, nil
}

// GetTickCount retrieves the number of milliseconds that have elapsed
// since the system was started.
func GetTickCount() uint32 {
	ret, _, _ := procGetTickCount.Call()
	return uint32(ret)
}

// GetIdleTime returns the number of milliseconds since the last input event.
func GetIdleTime() (uint32, error) {
	lastInput, err := GetLastInputInfo()
	if err != nil {
		return 0, err
	}

	current := GetTickCount()

	// Handle tick count overflow (approximately every 49.7 days)
	if current < lastInput {
		// Tick count wrapped around
		current += 0xFFFFFFFF
	}

	return current - lastInput, nil
}

// QueryUserNotificationState retrieves the current state of the user notification system.
// This is used for "Smart Full Stop" - detecting games and Do Not Disturb mode.
func QueryUserNotificationState() (uint32, error) {
	var state uint32
	ret, _, err := procSHQueryUserNotificationState.Call(
		uintptr(unsafe.Pointer(&state)),
	)
	if ret != 0 {
		return 0, fmt.Errorf("SHQueryUserNotificationState failed: %w", err)
	}

	return state, nil
}

// IsGameRunning checks if a full-screen DirectX/OpenGL game is running.
// This implements the "Smart Full Stop" feature.
func IsGameRunning() (bool, error) {
	state, err := QueryUserNotificationState()
	if err != nil {
		return false, err
	}

	// QUNS_RUNNING_D3D_FULL_SCREEN (3) indicates a full-screen game
	return state == QUNS_RUNNING_D3D_FULL_SCREEN, nil
}

// IsBusy checks if the user is in a busy state (e.g., presentation mode).
func IsBusy() (bool, error) {
	state, err := QueryUserNotificationState()
	if err != nil {
		return false, err
	}

	// QUNS_BUSY (2) indicates busy state
	return state == QUNS_BUSY, nil
}

// UTF16ToString converts a UTF-16 byte slice to a Go string.
// This is a helper function that handles null termination.
func UTF16ToString(s []uint16) string {
	for i, v := range s {
		if v == 0 {
			return string(utf16.Decode(s[:i]))
		}
	}
	return string(utf16.Decode(s))
}
