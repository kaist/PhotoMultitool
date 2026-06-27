#pragma once

#include <cstdint>
#include <functional>
#include <string>
#include <vector>
#include <windows.h>

class SerialMicropythonClient {
public:
    SerialMicropythonClient(std::wstring port, int baud_rate);
    ~SerialMicropythonClient();

    bool connect(std::wstring& error);
    void disconnect();

    bool list_dir(const std::wstring& path, std::vector<std::wstring>& entries, std::wstring& error);
    bool read_file(const std::wstring& remote_path, std::vector<std::uint8_t>& data, std::wstring& error,
                   const std::function<bool(size_t, size_t)>& progress = {});
    bool write_file(const std::wstring& remote_path, const std::vector<std::uint8_t>& data, std::wstring& error,
                    const std::function<bool(size_t, size_t)>& progress = {});
    bool remove_file(const std::wstring& remote_path, std::wstring& error);
    bool make_dir(const std::wstring& remote_path, std::wstring& error);
    bool remove_dir(const std::wstring& remote_path, std::wstring& error);
    bool rename_path(const std::wstring& old_path, const std::wstring& new_path, std::wstring& error);

private:
    void clear_state();
    bool configure_port(std::wstring& error);
    bool write_all(const std::string& data, std::wstring& error);
    bool write_all(const std::vector<std::uint8_t>& data, std::wstring& error);
    bool read_some(std::string& out, DWORD timeout_ms);
    bool read_exact(size_t count, std::string& out, DWORD timeout_ms, std::wstring& error);
    bool read_until(size_t min_num_bytes, const std::string& token, std::string& out, DWORD timeout_ms, std::wstring& error);
    bool read_until_byte(char token, std::string& out, DWORD timeout_ms, std::wstring& error);
    void drain_input();
    bool enter_raw_repl(std::wstring& error);
    void exit_raw_repl();
    bool exec_capture(const std::string& code, std::string& stdout_data, std::string& stderr_data, std::wstring& error);

    std::wstring port_;
    int baud_rate_;
    void* handle_;
    bool raw_repl_;
    std::string rx_buffer_;
};

std::string narrow_utf8(const std::wstring& value);
std::string narrow_ansi(const std::wstring& value);
std::wstring widen_utf8(const std::string& value);
std::wstring widen_ansi(const std::string& value);
std::string python_quote(const std::wstring& value);
std::string hex_encode(const std::vector<std::uint8_t>& data, size_t offset, size_t count);
std::string bytes_repr(const std::vector<std::uint8_t>& data, size_t offset, size_t count);
bool hex_decode_lines(const std::string& text, std::vector<std::uint8_t>& data);
