#include "SerialMicropythonClient.h"

#include <algorithm>
#include <chrono>
#include <sstream>
#include <windows.h>

namespace {

constexpr DWORD kReadTimeoutMs = 200;
constexpr DWORD kCommandTimeoutMs = 15000;

HANDLE as_handle(void* value)
{
    return reinterpret_cast<HANDLE>(value);
}

int hex_value(char ch)
{
    if (ch >= '0' && ch <= '9') {
        return ch - '0';
    }
    if (ch >= 'a' && ch <= 'f') {
        return 10 + (ch - 'a');
    }
    if (ch >= 'A' && ch <= 'F') {
        return 10 + (ch - 'A');
    }
    return -1;
}

}  // namespace

std::string narrow_utf8(const std::wstring& value)
{
    if (value.empty()) {
        return std::string();
    }
    int size_needed = WideCharToMultiByte(CP_UTF8, 0, value.c_str(), (int)value.size(), nullptr, 0, nullptr, nullptr);
    std::string result(size_needed, 0);
    WideCharToMultiByte(CP_UTF8, 0, value.c_str(), (int)value.size(), &result[0], size_needed, nullptr, nullptr);
    return result;
}

std::string narrow_ansi(const std::wstring& value)
{
    if (value.empty()) {
        return std::string();
    }
    int size_needed = WideCharToMultiByte(CP_ACP, 0, value.c_str(), (int)value.size(), nullptr, 0, nullptr, nullptr);
    std::string result(size_needed, 0);
    WideCharToMultiByte(CP_ACP, 0, value.c_str(), (int)value.size(), &result[0], size_needed, nullptr, nullptr);
    return result;
}

std::wstring widen_utf8(const std::string& value)
{
    if (value.empty()) {
        return std::wstring();
    }
    int size_needed = MultiByteToWideChar(CP_UTF8, 0, value.c_str(), (int)value.size(), nullptr, 0);
    std::wstring result(size_needed, 0);
    MultiByteToWideChar(CP_UTF8, 0, value.c_str(), (int)value.size(), &result[0], size_needed);
    return result;
}

std::wstring widen_ansi(const std::string& value)
{
    if (value.empty()) {
        return std::wstring();
    }
    int size_needed = MultiByteToWideChar(CP_ACP, 0, value.c_str(), (int)value.size(), nullptr, 0);
    std::wstring result(size_needed, 0);
    MultiByteToWideChar(CP_ACP, 0, value.c_str(), (int)value.size(), &result[0], size_needed);
    return result;
}

std::string python_quote(const std::wstring& value)
{
    std::string utf8 = narrow_utf8(value);
    std::string out = "'";
    for (unsigned char ch : utf8) {
        if (ch == '\\' || ch == '\'') {
            out.push_back('\\');
            out.push_back((char)ch);
        } else if (ch == '\r') {
            out += "\\r";
        } else if (ch == '\n') {
            out += "\\n";
        } else {
            out.push_back((char)ch);
        }
    }
    out.push_back('\'');
    return out;
}

std::string hex_encode(const std::vector<std::uint8_t>& data, size_t offset, size_t count)
{
    static const char* kHex = "0123456789abcdef";
    std::string out;
    out.reserve(count * 2);
    for (size_t i = 0; i < count; ++i) {
        std::uint8_t value = data[offset + i];
        out.push_back(kHex[value >> 4]);
        out.push_back(kHex[value & 0x0f]);
    }
    return out;
}

std::string bytes_repr(const std::vector<std::uint8_t>& data, size_t offset, size_t count)
{
    static const char* kHex = "0123456789abcdef";
    std::string out = "b'";
    out.reserve(2 + count * 4);
    for (size_t i = 0; i < count; ++i) {
        unsigned char ch = data[offset + i];
        if (ch == '\\' || ch == '\'') {
            out.push_back('\\');
            out.push_back((char)ch);
        } else if (ch >= 32 && ch <= 126) {
            out.push_back((char)ch);
        } else {
            out += "\\x";
            out.push_back(kHex[(ch >> 4) & 0x0f]);
            out.push_back(kHex[ch & 0x0f]);
        }
    }
    out.push_back('\'');
    return out;
}

bool hex_decode_lines(const std::string& text, std::vector<std::uint8_t>& data)
{
    std::string hex;
    hex.reserve(text.size());
    for (char ch : text) {
        if (ch == '\r' || ch == '\n') {
            continue;
        }
        hex.push_back(ch);
    }
    if ((hex.size() % 2) != 0) {
        return false;
    }
    data.clear();
    data.reserve(hex.size() / 2);
    for (size_t i = 0; i < hex.size(); i += 2) {
        int hi = hex_value(hex[i]);
        int lo = hex_value(hex[i + 1]);
        if (hi < 0 || lo < 0) {
            return false;
        }
        data.push_back((std::uint8_t)((hi << 4) | lo));
    }
    return true;
}

SerialMicropythonClient::SerialMicropythonClient(std::wstring port, int baud_rate)
    : port_(std::move(port)), baud_rate_(baud_rate), handle_(INVALID_HANDLE_VALUE), raw_repl_(false)
{
}

SerialMicropythonClient::~SerialMicropythonClient()
{
    disconnect();
}

void SerialMicropythonClient::clear_state()
{
    raw_repl_ = false;
    rx_buffer_.clear();
}

bool SerialMicropythonClient::configure_port(std::wstring& error)
{
    DCB dcb{};
    dcb.DCBlength = sizeof(dcb);
    if (!GetCommState(as_handle(handle_), &dcb)) {
        error = L"GetCommState failed";
        return false;
    }
    dcb.BaudRate = (DWORD)baud_rate_;
    dcb.ByteSize = 8;
    dcb.Parity = NOPARITY;
    dcb.StopBits = ONESTOPBIT;
    dcb.fBinary = TRUE;
    dcb.fDtrControl = DTR_CONTROL_ENABLE;
    dcb.fRtsControl = RTS_CONTROL_ENABLE;
    if (!SetCommState(as_handle(handle_), &dcb)) {
        error = L"SetCommState failed";
        return false;
    }

    COMMTIMEOUTS timeouts{};
    timeouts.ReadIntervalTimeout = 50;
    timeouts.ReadTotalTimeoutConstant = 50;
    timeouts.ReadTotalTimeoutMultiplier = 10;
    timeouts.WriteTotalTimeoutConstant = 200;
    timeouts.WriteTotalTimeoutMultiplier = 10;
    if (!SetCommTimeouts(as_handle(handle_), &timeouts)) {
        error = L"SetCommTimeouts failed";
        return false;
    }

    SetupComm(as_handle(handle_), 16 * 1024, 16 * 1024);
    PurgeComm(as_handle(handle_), PURGE_RXCLEAR | PURGE_TXCLEAR);
    return true;
}

bool SerialMicropythonClient::connect(std::wstring& error)
{
    disconnect();
    std::wstring device = port_;
    if (device.rfind(L"\\\\.\\", 0) != 0) {
        device = L"\\\\.\\" + device;
    }
    HANDLE serial = CreateFileW(device.c_str(), GENERIC_READ | GENERIC_WRITE, 0, nullptr, OPEN_EXISTING, 0, nullptr);
    if (serial == INVALID_HANDLE_VALUE) {
        error = L"Cannot open port " + port_;
        return false;
    }
    handle_ = serial;
    clear_state();
    return configure_port(error);
}

void SerialMicropythonClient::disconnect()
{
    HANDLE serial = as_handle(handle_);
    if (serial != INVALID_HANDLE_VALUE) {
        if (raw_repl_) {
            exit_raw_repl();
        }
        CloseHandle(serial);
    }
    handle_ = INVALID_HANDLE_VALUE;
    clear_state();
}

bool SerialMicropythonClient::write_all(const std::string& data, std::wstring& error)
{
    std::vector<std::uint8_t> bytes(data.begin(), data.end());
    return write_all(bytes, error);
}

bool SerialMicropythonClient::write_all(const std::vector<std::uint8_t>& data, std::wstring& error)
{
    HANDLE serial = as_handle(handle_);
    size_t offset = 0;
    while (offset < data.size()) {
        DWORD written = 0;
        if (!WriteFile(serial, data.data() + offset, (DWORD)std::min<size_t>(4096, data.size() - offset), &written, nullptr)) {
            error = L"WriteFile failed";
            return false;
        }
        offset += written;
    }
    return true;
}

bool SerialMicropythonClient::read_some(std::string& out, DWORD timeout_ms)
{
    HANDLE serial = as_handle(handle_);
    auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
    char buf[512];
    while (std::chrono::steady_clock::now() < deadline) {
        DWORD read = 0;
        if (!ReadFile(serial, buf, sizeof(buf), &read, nullptr)) {
            return false;
        }
        if (read > 0) {
            out.append(buf, buf + read);
            return true;
        }
        Sleep(10);
    }
    return true;
}

bool SerialMicropythonClient::read_exact(size_t count, std::string& out, DWORD timeout_ms, std::wstring& error)
{
    auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
    while (rx_buffer_.size() < count && std::chrono::steady_clock::now() < deadline) {
        std::string chunk;
        if (!read_some(chunk, kReadTimeoutMs)) {
            error = L"ReadFile failed";
            return false;
        }
        if (!chunk.empty()) {
            rx_buffer_ += chunk;
        } else {
            Sleep(10);
        }
    }
    if (rx_buffer_.size() < count) {
        error = L"Timeout waiting for exact data";
        return false;
    }
    out.assign(rx_buffer_.data(), count);
    rx_buffer_.erase(0, count);
    return true;
}

bool SerialMicropythonClient::read_until(size_t min_num_bytes, const std::string& token, std::string& out, DWORD timeout_ms, std::wstring& error)
{
    out.clear();
    auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
    while (rx_buffer_.size() < min_num_bytes && std::chrono::steady_clock::now() < deadline) {
        std::string chunk;
        if (!read_some(chunk, kReadTimeoutMs)) {
            error = L"ReadFile failed";
            return false;
        }
        if (!chunk.empty()) {
            rx_buffer_ += chunk;
        }
    }
    while (std::chrono::steady_clock::now() < deadline) {
        auto pos = rx_buffer_.find(token);
        if (pos != std::string::npos && pos + token.size() >= min_num_bytes) {
            out.assign(rx_buffer_.data(), pos + token.size());
            rx_buffer_.erase(0, pos + token.size());
            return true;
        }
        std::string chunk;
        if (!read_some(chunk, kReadTimeoutMs)) {
            error = L"ReadFile failed";
            return false;
        }
        if (!chunk.empty()) {
            rx_buffer_ += chunk;
        } else {
            Sleep(10);
        }
    }
    error = L"Timeout waiting for device response";
    return false;
}

bool SerialMicropythonClient::read_until_byte(char token, std::string& out, DWORD timeout_ms, std::wstring& error)
{
    auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
    while (std::chrono::steady_clock::now() < deadline) {
        auto pos = rx_buffer_.find(token);
        if (pos != std::string::npos) {
            out.assign(rx_buffer_.data(), pos);
            rx_buffer_.erase(0, pos + 1);
            return true;
        }
        std::string chunk;
        if (!read_some(chunk, kReadTimeoutMs)) {
            error = L"ReadFile failed";
            return false;
        }
        if (!chunk.empty()) {
            rx_buffer_ += chunk;
        } else {
            Sleep(10);
        }
    }
    error = L"Timeout waiting for EOF";
    return false;
}

void SerialMicropythonClient::drain_input()
{
    rx_buffer_.clear();
    for (int i = 0; i < 5; ++i) {
        std::string chunk;
        if (!read_some(chunk, 50)) {
            break;
        }
        if (chunk.empty()) {
            break;
        }
    }
}

bool SerialMicropythonClient::enter_raw_repl(std::wstring& error)
{
    if (raw_repl_) {
        return true;
    }
    drain_input();
    if (!write_all("\r\x03", error)) {
        return false;
    }
    Sleep(100);
    if (!write_all("\x03", error)) {
        return false;
    }
    Sleep(100);
    drain_input();

    std::string response;
    bool entered = false;
    for (int retry = 0; retry < 5; ++retry) {
        if (!write_all("\r\x01", error)) {
            return false;
        }
        response.clear();
        if (read_until(1, "raw REPL; CTRL-B to exit\r\n>", response, 3000, error) &&
            response.size() >= std::string("raw REPL; CTRL-B to exit\r\n>").size() &&
            response.compare(response.size() - std::string("raw REPL; CTRL-B to exit\r\n>").size(),
                             std::string("raw REPL; CTRL-B to exit\r\n>").size(),
                             "raw REPL; CTRL-B to exit\r\n>") == 0) {
            entered = true;
            break;
        }
        Sleep(200);
    }
    if (!entered) {
        if (error.empty()) {
            error = L"Timeout entering raw REPL";
        } else {
            error = L"Timeout entering raw REPL: " + error;
        }
        return false;
    }
    if (!write_all("\x04", error)) {
        return false;
    }
    response.clear();
    if (!read_until(1, "soft reboot\r\n", response, 5000, error)) {
        error = L"Timeout waiting for soft reboot: " + error;
        return false;
    }
    Sleep(500);
    if (!write_all("\x03", error)) {
        return false;
    }
    Sleep(100);
    if (!write_all("\x03", error)) {
        return false;
    }
    response.clear();
    if (!read_until(1, "raw REPL; CTRL-B to exit\r\n", response, 5000, error)) {
        error = L"Timeout waiting for raw REPL after reboot: " + error;
        return false;
    }
    raw_repl_ = true;
    return true;
}

void SerialMicropythonClient::exit_raw_repl()
{
    std::wstring ignored;
    write_all("\x02", ignored);
    raw_repl_ = false;
    drain_input();
}

bool SerialMicropythonClient::exec_capture(const std::string& code, std::string& stdout_data, std::string& stderr_data, std::wstring& error)
{
    if (!enter_raw_repl(error)) {
        return false;
    }
    std::string prompt;
    if (!read_until(1, ">", prompt, 3000, error)) {
        error = L"Timeout waiting for prompt before exec: " + error;
        return false;
    }
    for (size_t i = 0; i < code.size(); i += 256) {
        size_t count = std::min<size_t>(256, code.size() - i);
        std::vector<std::uint8_t> chunk(code.begin() + i, code.begin() + i + count);
        if (!write_all(chunk, error)) {
            return false;
        }
        Sleep(10);
    }
    if (!write_all("\x04", error)) {
        return false;
    }

    std::string okbuf;
    if (!read_exact(2, okbuf, 3000, error) || okbuf != "OK") {
        if (okbuf.empty()) {
            error = L"Could not exec command: " + error;
        } else {
            error = L"Could not exec command, got: " + widen_ansi(okbuf);
        }
        return false;
    }
    stdout_data.clear();
    stderr_data.clear();
    if (!read_until_byte(0x04, stdout_data, kCommandTimeoutMs, error)) {
        error = L"Timeout waiting for first EOF: " + error;
        return false;
    }
    if (!read_until_byte(0x04, stderr_data, kCommandTimeoutMs, error)) {
        error = L"Timeout waiting for second EOF: " + error;
        return false;
    }
    return true;
}

bool SerialMicropythonClient::list_dir(const std::wstring& path, std::vector<std::wstring>& entries, std::wstring& error)
{
    std::ostringstream script;
    script
        << "import os\r\n"
        << "p=" << python_quote(path) << "\r\n"
        << "r=[]\r\n"
        << "for x in os.listdir(p):\r\n"
        << " full=(p.rstrip('/')+'/'+x) if p!='/' else '/'+x\r\n"
        << " try:\r\n"
        << "  m=os.stat(full)[0]\r\n"
        << " except OSError:\r\n"
        << "  m=0\r\n"
        << " r.append(x+('/' if (m&0x4000) else ''))\r\n"
        << "print('\\n'.join(r))\r\n";

    std::string stdout_data;
    std::string stderr_data;
    if (!exec_capture(script.str(), stdout_data, stderr_data, error)) {
        return false;
    }
    if (!stderr_data.empty()) {
        error = widen_utf8(stderr_data);
        return false;
    }

    entries.clear();
    std::istringstream ss(stdout_data);
    std::string line;
    while (std::getline(ss, line)) {
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }
        if (!line.empty()) {
            entries.push_back(widen_utf8(line));
        }
    }
    return true;
}

bool SerialMicropythonClient::read_file(const std::wstring& remote_path, std::vector<std::uint8_t>& data, std::wstring& error,
                                        const std::function<bool(size_t, size_t)>& progress)
{
    std::ostringstream script;
    script
        << "import sys\r\n"
        << "import os\r\n"
        << "import ubinascii\r\n"
        << "print(os.stat(" << python_quote(remote_path) << ")[6])\r\n"
        << "f=open(" << python_quote(remote_path) << ",'rb')\r\n"
        << "while True:\r\n"
        << " b=f.read(256)\r\n"
        << " if not b:\r\n"
        << "  break\r\n"
        << " sys.stdout.write(ubinascii.hexlify(b))\r\n"
        << "f.close()\r\n";

    std::string stdout_data;
    std::string stderr_data;
    if (!exec_capture(script.str(), stdout_data, stderr_data, error)) {
        return false;
    }
    if (!stderr_data.empty()) {
        error = widen_utf8(stderr_data);
        return false;
    }
    auto nl = stdout_data.find("\r\n");
    if (nl == std::string::npos) {
        nl = stdout_data.find('\n');
    }
    size_t total = 0;
    std::string payload = stdout_data;
    if (nl != std::string::npos) {
        try {
            total = (size_t)std::stoull(stdout_data.substr(0, nl));
        } catch (...) {
            total = 0;
        }
        payload = stdout_data.substr(nl + ((stdout_data[nl] == '\r' && nl + 1 < stdout_data.size() && stdout_data[nl + 1] == '\n') ? 2 : 1));
    }
    if (!hex_decode_lines(payload, data)) {
        error = L"Cannot decode file data";
        return false;
    }
    if (progress) {
        progress(data.size(), total ? total : data.size());
    }
    return true;
}

bool SerialMicropythonClient::write_file(const std::wstring& remote_path, const std::vector<std::uint8_t>& data, std::wstring& error,
                                         const std::function<bool(size_t, size_t)>& progress)
{
    {
        std::ostringstream script;
        script
            << "import os\r\n"
            << "import ubinascii\r\n"
            << "p=" << python_quote(remote_path) << "\r\n"
            << "parts=p.split('/')[:-1]\r\n"
            << "cur=''\r\n"
            << "for part in parts:\r\n"
            << " if not part:\r\n"
            << "  cur='/'\r\n"
            << "  continue\r\n"
            << " cur=(cur+part) if cur=='/' else ((cur+'/'+part) if cur else ('/'+part))\r\n"
            << " try:\r\n"
            << "  os.mkdir(cur)\r\n"
            << " except OSError:\r\n"
            << "  pass\r\n"
            << "uh=ubinascii.unhexlify\r\n"
            << "f=open(" << python_quote(remote_path) << ",'wb')\r\n";
        std::string stdout_data;
        std::string stderr_data;
        if (!exec_capture(script.str(), stdout_data, stderr_data, error)) {
            return false;
        }
        if (!stderr_data.empty()) {
            error = widen_utf8(stderr_data);
            return false;
        }
    }

    const size_t chunk_size = 1024;
    if (progress) {
        progress(0, data.size());
    }
    for (size_t offset = 0; offset < data.size(); offset += chunk_size) {
        size_t count = std::min(chunk_size, data.size() - offset);
        std::string script = "f.write(uh('" + hex_encode(data, offset, count) + "'))\r\n";
        std::string stdout_data;
        std::string stderr_data;
        if (!exec_capture(script, stdout_data, stderr_data, error)) {
            return false;
        }
        if (!stderr_data.empty()) {
            error = widen_utf8(stderr_data);
            return false;
        }
        if (progress && !progress(offset + count, data.size())) {
            error = L"Transfer aborted";
            return false;
        }
    }
    {
        std::string stdout_data;
        std::string stderr_data;
        if (!exec_capture("f.close()\r\n", stdout_data, stderr_data, error)) {
            return false;
        }
        if (!stderr_data.empty()) {
            error = widen_utf8(stderr_data);
            return false;
        }
    }
    return true;
}

bool SerialMicropythonClient::remove_file(const std::wstring& remote_path, std::wstring& error)
{
    std::ostringstream script;
    script << "import os\r\nos.remove(" << python_quote(remote_path) << ")\r\n";
    std::string stdout_data;
    std::string stderr_data;
    if (!exec_capture(script.str(), stdout_data, stderr_data, error)) {
        return false;
    }
    if (!stderr_data.empty()) {
        error = widen_utf8(stderr_data);
        return false;
    }
    return true;
}

bool SerialMicropythonClient::make_dir(const std::wstring& remote_path, std::wstring& error)
{
    std::ostringstream script;
    script
        << "import os\r\n"
        << "p=" << python_quote(remote_path) << "\r\n"
        << "parts=p.split('/')\r\n"
        << "cur=''\r\n"
        << "for part in parts:\r\n"
        << " if not part:\r\n"
        << "  cur='/'\r\n"
        << "  continue\r\n"
        << " cur=(cur+part) if cur=='/' else ((cur+'/'+part) if cur else ('/'+part))\r\n"
        << " try:\r\n"
        << "  os.mkdir(cur)\r\n"
        << " except OSError:\r\n"
        << "  pass\r\n";
    std::string stdout_data;
    std::string stderr_data;
    if (!exec_capture(script.str(), stdout_data, stderr_data, error)) {
        return false;
    }
    if (!stderr_data.empty()) {
        error = widen_utf8(stderr_data);
        return false;
    }
    return true;
}

bool SerialMicropythonClient::remove_dir(const std::wstring& remote_path, std::wstring& error)
{
    std::ostringstream script;
    script << "import os\r\nos.rmdir(" << python_quote(remote_path) << ")\r\n";
    std::string stdout_data;
    std::string stderr_data;
    if (!exec_capture(script.str(), stdout_data, stderr_data, error)) {
        return false;
    }
    if (!stderr_data.empty()) {
        error = widen_utf8(stderr_data);
        return false;
    }
    return true;
}

bool SerialMicropythonClient::rename_path(const std::wstring& old_path, const std::wstring& new_path, std::wstring& error)
{
    std::ostringstream script;
    script
        << "import os\r\n"
        << "os.rename(" << python_quote(old_path) << "," << python_quote(new_path) << ")\r\n";
    std::string stdout_data;
    std::string stderr_data;
    if (!exec_capture(script.str(), stdout_data, stderr_data, error)) {
        return false;
    }
    if (!stderr_data.empty()) {
        error = widen_utf8(stderr_data);
        return false;
    }
    return true;
}
