// Build through prepare_game.py against CascLib. Only local storage is opened.
#include "CascLib.h"
#include <algorithm>
#include <array>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

namespace fs = std::filesystem;

static std::string hex(const BYTE *bytes) {
    const char digits[] = "0123456789abcdef";
    std::string value;
    for (int i = 0; i < MD5_HASH_SIZE; ++i) {
        value += digits[bytes[i] >> 4];
        value += digits[bytes[i] & 15];
    }
    return value;
}

static bool inventory(HANDLE storage, const char *destination) {
    std::ofstream output(destination);
    CASC_FIND_DATA record{};
    HANDLE search = CascFindFirstFile(storage, "*", &record, nullptr);
    if (!output || !search || search == INVALID_HANDLE_VALUE) return false;
    output << "local\tbytes\tckey\tpath\n";
    do {
        if (record.NameType == CascNameFull) {
            output << record.bFileAvailable << '\t' << record.FileSize << '\t'
                   << hex(record.CKey) << '\t' << record.szFileName << '\n';
        }
    } while (CascFindNextFile(search, &record));
    CascFindClose(search);
    return output.good();
}

static bool extract(HANDLE storage, const std::string &source, const fs::path &dest) {
    HANDLE file = nullptr;
    if (!CascOpenFile(storage, source.c_str(), 0, CASC_OPEN_BY_NAME, &file)) return false;
    ULONGLONG expected = 0;
    bool ok = CascGetFileSize64(file, &expected);
    fs::create_directories(dest.parent_path());
    const fs::path staging = dest.string() + ".partial";
    std::ofstream output(staging, std::ios::binary);
    std::array<char, 64 * 1024> chunk{};
    ULONGLONG total = 0;
    while (ok && output && total < expected) {
        DWORD got = 0;
        DWORD wanted = static_cast<DWORD>(std::min<ULONGLONG>(chunk.size(), expected - total));
        ok = CascReadFile(file, chunk.data(), wanted, &got) && got > 0;
        if (ok) {
            output.write(chunk.data(), got);
            total += got;
        }
    }
    CascCloseFile(file);
    output.close();
    if (ok && output && total == expected) {
        fs::rename(staging, dest);
        return true;
    }
    fs::remove(staging);
    return false;
}

int main(int argc, char **argv) {
    if (argc != 4) {
        std::cerr << "Usage: casc_reader inventory|extract STORAGE TSV\n";
        return 2;
    }
    HANDLE storage = nullptr;
    if (!CascOpenStorage(argv[2], 0, &storage)) {
        std::cerr << "Cannot open local storage, CascLib error " << GetCascError() << '\n';
        return 1;
    }
    bool ok = false;
    if (std::string(argv[1]) == "inventory") {
        ok = inventory(storage, argv[3]);
    } else if (std::string(argv[1]) == "extract") {
        std::ifstream plan(argv[3]);
        ok = plan.good();
        std::string line;
        while (std::getline(plan, line)) {
            auto split = line.find('\t');
            if (split == std::string::npos || !extract(storage, line.substr(0, split), line.substr(split + 1))) {
                std::cerr << "Could not fully extract " << line.substr(0, split) << '\n';
                ok = false;
            }
        }
    }
    CascCloseStorage(storage);
    return ok ? 0 : 1;
}
