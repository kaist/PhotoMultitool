#pragma once

#include <string>
#include <vector>
#include <windows.h>

std::wstring widen(const std::string& s);
std::wstring widen_ansi(const std::string& s);
std::wstring quote_arg(const std::wstring& s);
int run_process(const std::wstring& executable, const std::vector<std::wstring>& args, std::wstring& output);
