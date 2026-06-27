#include "MyAmpy.h"
#include "SerialMicropythonClient.h"

#include <fstream>
#include <memory>
#include <string>
#include <vector>

static std::wstring g_port = L"COM3";
static int g_baud = 115200;
static std::unique_ptr<SerialMicropythonClient> g_client;
static int g_plugin_number = 0;
static tProgressProc g_progress_proc = nullptr;

struct FindState {
    std::vector<std::wstring> entries;
    size_t index = 0;
};

static std::wstring module_dir()
{
    HMODULE hm = nullptr;
    wchar_t path[MAX_PATH] = {};
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                            reinterpret_cast<LPCWSTR>(&module_dir), &hm)) {
        return L".";
    }
    DWORD len = GetModuleFileNameW(hm, path, MAX_PATH);
    if (!len || len >= MAX_PATH) {
        return L".";
    }
    std::wstring full(path, len);
    auto pos = full.find_last_of(L"\\/");
    return pos == std::wstring::npos ? L"." : full.substr(0, pos);
}

static void load_config()
{
    std::wstring ini_path = module_dir() + L"\\plugin.ini";
    std::wifstream f(ini_path.c_str());
    if (!f) {
        return;
    }

    std::wstring line;
    while (std::getline(f, line)) {
        if (line.rfind(L"Port=", 0) == 0) {
            g_port = line.substr(5);
        } else if (line.rfind(L"Baud=", 0) == 0) {
            try {
                g_baud = std::stoi(line.substr(5));
            } catch (...) {
                g_baud = 115200;
            }
        }
    }
}

static std::wstring normalize_remote(const char* path)
{
    std::wstring remote;
    if (path && path[0]) {
        remote = widen_ansi(std::string(path));
    }
    for (auto& ch : remote) {
        if (ch == L'\\') {
            ch = L'/';
        }
    }
    if (remote.empty() || remote == L"/") {
        return L"/flash";
    }
    if (remote.rfind(L"/flash", 0) == 0) {
        return remote;
    }
    if (!remote.empty() && remote[0] == L'/') {
        return L"/flash" + remote;
    }
    return L"/flash/" + remote;
}

static bool fill_find_data(const std::wstring& entry, WIN32_FIND_DATAA* data)
{
    if (!data) {
        return false;
    }
    ZeroMemory(data, sizeof(WIN32_FIND_DATAA));
    std::wstring name = entry;
    bool is_dir = false;
    if (!name.empty() && name.back() == L'/') {
        is_dir = true;
        name.pop_back();
    }
    std::string ansi_name = narrow_ansi(name);
    if (ansi_name.empty()) {
        return false;
    }
    strncpy_s(data->cFileName, ansi_name.c_str(), sizeof(data->cFileName) - 1);
    data->dwFileAttributes = is_dir ? FILE_ATTRIBUTE_DIRECTORY : FILE_ATTRIBUTE_ARCHIVE;
    return true;
}

static HANDLE make_find_handle(const std::vector<std::wstring>& entries, WIN32_FIND_DATAA* data)
{
    if (entries.empty()) {
        return INVALID_HANDLE_VALUE;
    }
    std::unique_ptr<FindState> state(new FindState());
    state->entries = entries;
    if (!fill_find_data(entries[0], data)) {
        return INVALID_HANDLE_VALUE;
    }
    return reinterpret_cast<HANDLE>(state.release());
}

static SerialMicropythonClient* acquire_client(std::wstring& error)
{
    if (g_client) {
        return g_client.get();
    }
    std::unique_ptr<SerialMicropythonClient> client(new SerialMicropythonClient(g_port, g_baud));
    if (!client->connect(error)) {
        return nullptr;
    }
    g_client = std::move(client);
    return g_client.get();
}

static void drop_client()
{
    if (g_client) {
        g_client->disconnect();
        g_client.reset();
    }
}

static void show_error(const wchar_t* prefix, const std::wstring& detail)
{
    std::wstring msg(prefix);
    if (!detail.empty()) {
        msg += L":\n\n";
        msg += detail;
    }
    MessageBoxW(nullptr, msg.c_str(), L"MyAmpy", MB_ICONERROR);
}

static bool report_progress(const char* source_name, const char* target_name, size_t done, size_t total)
{
    if (!g_progress_proc) {
        return true;
    }
    int percent = 0;
    if (total > 0) {
        percent = (int)((done * 100) / total);
        if (percent > 100) {
            percent = 100;
        }
    }
    return g_progress_proc(g_plugin_number,
                           const_cast<char*>(source_name ? source_name : ""),
                           const_cast<char*>(target_name ? target_name : ""),
                           percent) == 0;
}

extern "C" {

int __stdcall FsInit(int PluginNr, tProgressProc pProgressProc, tLogProc /*pLogProc*/, tRequestProc /*pRequestProc*/)
{
    g_plugin_number = PluginNr;
    g_progress_proc = pProgressProc;
    load_config();
    drop_client();
    return 0;
}

HANDLE __stdcall FsFindFirst(char* Path, WIN32_FIND_DATAA* FindData)
{
    std::wstring error;
    auto client = acquire_client(error);
    if (!client) {
        show_error(L"Cannot open device", error);
        return INVALID_HANDLE_VALUE;
    }

    std::vector<std::wstring> entries;
    if (!client->list_dir(normalize_remote(Path), entries, error)) {
        drop_client();
        show_error(L"List error", error);
        return INVALID_HANDLE_VALUE;
    }
    return make_find_handle(entries, FindData);
}

BOOL __stdcall FsFindNext(HANDLE Hdl, WIN32_FIND_DATAA* FindData)
{
    auto* state = reinterpret_cast<FindState*>(Hdl);
    if (!state) {
        return FALSE;
    }
    state->index++;
    if (state->index >= state->entries.size()) {
        return FALSE;
    }
    return fill_find_data(state->entries[state->index], FindData) ? TRUE : FALSE;
}

int __stdcall FsFindClose(HANDLE Hdl)
{
    delete reinterpret_cast<FindState*>(Hdl);
    return 0;
}

int __stdcall FsGetFile(char* RemoteName, char* LocalName, int CopyFlags, RemoteInfoStruct* /*ri*/)
{
    std::wstring error;
    auto client = acquire_client(error);
    if (!client) {
        show_error(L"Cannot open device", error);
        return FS_FILE_NOTFOUND;
    }

    std::vector<std::uint8_t> data;
    report_progress(RemoteName, LocalName, 0, 100);
    if (!client->read_file(normalize_remote(RemoteName), data, error,
                           [RemoteName, LocalName](size_t done, size_t total) {
                               return report_progress(RemoteName, LocalName, done, total);
                           })) {
        drop_client();
        show_error(L"Get error", error);
        return FS_FILE_READERROR;
    }

    HANDLE file = CreateFileA(LocalName, GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        return FS_FILE_WRITEERROR;
    }
    DWORD written = 0;
    BOOL ok = data.empty() ? TRUE : WriteFile(file, data.data(), (DWORD)data.size(), &written, nullptr);
    CloseHandle(file);
    if (!ok || written != data.size()) {
        return FS_FILE_WRITEERROR;
    }

    if (CopyFlags & FS_COPYFLAGS_MOVE) {
        client->remove_file(normalize_remote(RemoteName), error);
    }
    report_progress(RemoteName, LocalName, 100, 100);
    return FS_FILE_OK;
}

int __stdcall FsPutFile(char* LocalName, char* RemoteName, int /*CopyFlags*/)
{
    HANDLE file = CreateFileA(LocalName, GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        return FS_FILE_NOTFOUND;
    }
    LARGE_INTEGER size{};
    if (!GetFileSizeEx(file, &size) || size.QuadPart < 0) {
        CloseHandle(file);
        return FS_FILE_READERROR;
    }
    std::vector<std::uint8_t> data((size_t)size.QuadPart);
    DWORD read = 0;
    BOOL ok = data.empty() ? TRUE : ReadFile(file, data.data(), (DWORD)data.size(), &read, nullptr);
    CloseHandle(file);
    if (!ok || read != data.size()) {
        return FS_FILE_READERROR;
    }

    std::wstring error;
    auto client = acquire_client(error);
    if (!client) {
        show_error(L"Cannot open device", error);
        return FS_FILE_WRITEERROR;
    }
    report_progress(LocalName, RemoteName, 0, data.size() ? data.size() : 100);
    if (!client->write_file(normalize_remote(RemoteName), data, error,
                            [LocalName, RemoteName](size_t done, size_t total) {
                                return report_progress(LocalName, RemoteName, done, total);
                            })) {
        drop_client();
        show_error(L"Put error", error);
        return FS_FILE_WRITEERROR;
    }
    report_progress(LocalName, RemoteName, data.size() ? data.size() : 100, data.size() ? data.size() : 100);
    return FS_FILE_OK;
}

BOOL __stdcall FsDeleteFile(char* RemoteName)
{
    std::wstring error;
    auto client = acquire_client(error);
    if (!client) {
        show_error(L"Cannot open device", error);
        return FALSE;
    }
    if (!client->remove_file(normalize_remote(RemoteName), error)) {
        drop_client();
        show_error(L"Delete error", error);
        return FALSE;
    }
    return TRUE;
}

BOOL __stdcall FsMkDir(char* Path)
{
    std::wstring error;
    auto client = acquire_client(error);
    if (!client) {
        show_error(L"Cannot open device", error);
        return FALSE;
    }
    if (!client->make_dir(normalize_remote(Path), error)) {
        drop_client();
        show_error(L"Mkdir error", error);
        return FALSE;
    }
    return TRUE;
}

BOOL __stdcall FsRemoveDir(char* RemoteName)
{
    std::wstring error;
    auto client = acquire_client(error);
    if (!client) {
        show_error(L"Cannot open device", error);
        return FALSE;
    }
    if (!client->remove_dir(normalize_remote(RemoteName), error)) {
        drop_client();
        show_error(L"Rmdir error", error);
        return FALSE;
    }
    return TRUE;
}

int __stdcall FsRenMovFile(char* OldName, char* NewName, BOOL /*Move*/, BOOL /*OverWrite*/, RemoteInfoStruct* /*ri*/)
{
    std::wstring error;
    auto client = acquire_client(error);
    if (!client) {
        show_error(L"Cannot open device", error);
        return FS_FILE_WRITEERROR;
    }
    if (!client->rename_path(normalize_remote(OldName), normalize_remote(NewName), error)) {
        drop_client();
        show_error(L"Rename error", error);
        return FS_FILE_WRITEERROR;
    }
    return FS_FILE_OK;
}

BOOL __stdcall FsDisconnect(char* /*DisconnectRoot*/)
{
    drop_client();
    return TRUE;
}

void __stdcall FsStatusInfo(char* /*RemoteDir*/, int /*InfoStartEnd*/, int /*InfoOperation*/)
{
}

void __stdcall FsGetDefRootName(char* DefRootName, int maxlen)
{
    if (DefRootName && maxlen > 0) {
        strncpy_s(DefRootName, maxlen, "flash", _TRUNCATE);
    }
}

void __stdcall FsSetCryptCallback(tCryptProc /*pCryptProc*/, int /*CryptoNr*/, int /*Flags*/)
{
}

void __stdcall FsSetDefaultParams(FsDefaultParamStruct* /*dps*/)
{
}

}
