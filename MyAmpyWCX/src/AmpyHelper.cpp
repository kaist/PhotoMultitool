#include "AmpyHelper.h"

#include <windows.h>
#include <sstream>

std::wstring widen(const std::string& s)
{
    int sz = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, nullptr, 0);
    std::wstring ws(sz, 0);
    MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, &ws[0], sz);
    ws.resize(sz - 1);
    return ws;
}

std::wstring widen_ansi(const std::string& s)
{
    int sz = MultiByteToWideChar(CP_ACP, 0, s.c_str(), -1, nullptr, 0);
    std::wstring ws(sz, 0);
    MultiByteToWideChar(CP_ACP, 0, s.c_str(), -1, &ws[0], sz);
    ws.resize(sz - 1);
    return ws;
}

std::wstring quote_arg(const std::wstring& s)
{
    if (s.find_first_of(L" \t\"") == std::wstring::npos) {
        return s;
    }
    std::wstring out = L"\"";
    for (wchar_t ch : s) {
        if (ch == L'"') {
            out += L'\\';
        }
        out += ch;
    }
    out += L"\"";
    return out;
}

int run_process(const std::wstring& executable, const std::vector<std::wstring>& args, std::wstring& output)
{
    std::wstring cmd = quote_arg(executable);
    for (const auto& a : args) {
        cmd += L" ";
        cmd += quote_arg(a);
    }

    SECURITY_ATTRIBUTES sa{ sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE };
    HANDLE hRead = nullptr;
    HANDLE hWrite = nullptr;
    if (!CreatePipe(&hRead, &hWrite, &sa, 0)) {
        return -1;
    }

    STARTUPINFOW si{};
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdOutput = hWrite;
    si.hStdError = hWrite;
    si.hStdInput = GetStdHandle(STD_INPUT_HANDLE);

    PROCESS_INFORMATION pi{};
    std::wstring mutable_cmd = cmd;
    BOOL ok = CreateProcessW(nullptr, &mutable_cmd[0], nullptr, nullptr, TRUE,
                             CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi);
    CloseHandle(hWrite);
    if (!ok) {
        CloseHandle(hRead);
        return -1;
    }

    std::string result;
    const DWORD bufSize = 4096;
    char buf[bufSize];
    DWORD read = 0;
    while (ReadFile(hRead, buf, sizeof(buf), &read, nullptr) && read) {
        result.append(buf, read);
    }
    CloseHandle(hRead);
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD exitCode = 0;
    GetExitCodeProcess(pi.hProcess, &exitCode);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    output = widen_ansi(result);
    return static_cast<int>(exitCode);
}
