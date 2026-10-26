// Native Windows entry point for the Windows-only launcher frontend.
// No GTK, POSIX process code, game assets, or user-specific paths are embedded.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <shellapi.h>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>
namespace fs = std::filesystem;
std::wstring quote(const std::wstring& s) {
    std::wstring out=L"\""; size_t slashes=0;
    for(wchar_t c:s) {
        if(c==L'\\') { ++slashes; continue; }
        if(c==L'\"') out.append(slashes*2+1,L'\\'); else out.append(slashes,L'\\');
        slashes=0; out+=c;
    }
    out.append(slashes*2,L'\\'); return out+L'\"';
}
std::wstring environment(const wchar_t* name) {
    DWORD n=GetEnvironmentVariableW(name,nullptr,0); if(!n) return {};
    std::wstring result(n,L'\0'); GetEnvironmentVariableW(name,result.data(),n); result.resize(n-1); return result;
}
fs::path python(const fs::path& folder) {
    if(auto value=environment(L"TTT2_PYTHON"); !value.empty()) {
        if(!fs::is_regular_file(value)) throw std::runtime_error("TTT2_PYTHON does not name a Python executable.");
        return value;
    }
    const auto portable=folder.parent_path()/"local/windows-tools/python-runtime/python/python.exe";
    if(fs::is_regular_file(portable)) return portable;
    for(HKEY hive:{HKEY_CURRENT_USER,HKEY_LOCAL_MACHINE}) {
        HKEY parent;
        if(RegOpenKeyExW(hive,L"Software\\Python\\PythonCore",0,KEY_READ,&parent)!=ERROR_SUCCESS) continue;
        wchar_t version[256]; DWORD length;
        std::vector<std::wstring> versions;
        for(DWORD i=0;;++i) {
            length=256;
            if(RegEnumKeyExW(parent,i,version,&length,nullptr,nullptr,nullptr,nullptr)!=ERROR_SUCCESS) break;
            if(version[0]==L'3') versions.emplace_back(version);
        }
        for(auto it=versions.rbegin();it!=versions.rend();++it) {
            HKEY key;
            if(RegOpenKeyExW(parent,(*it+L"\\InstallPath").c_str(),0,KEY_READ,&key)!=ERROR_SUCCESS) continue;
            wchar_t path[32768]; DWORD bytes=sizeof(path),type=0;
            const auto result=RegQueryValueExW(key,L"ExecutablePath",nullptr,&type,reinterpret_cast<BYTE*>(path),&bytes);
            RegCloseKey(key);
            if(result==ERROR_SUCCESS && type==REG_SZ && fs::is_regular_file(path)) { RegCloseKey(parent); return path; }
        }
        RegCloseKey(parent);
    }
    wchar_t found[32768];
    if(SearchPathW(nullptr,L"python.exe",nullptr,32768,found,nullptr) && fs::is_regular_file(found)) return found;
    throw std::runtime_error("Install Python 3 with Tcl/Tk from python.org, or set TTT2_PYTHON to its python.exe.");
}
int WINAPI wWinMain(HINSTANCE,HINSTANCE,PWSTR,int) {
    try {
        wchar_t self[32768]; DWORD n=GetModuleFileNameW(nullptr,self,32768);
        if(!n || n>=32768) throw std::runtime_error("Cannot locate Ultimate Launcher.");
        fs::path folder=fs::path(self).parent_path();
        fs::path script=folder.parent_path()/"launcher/windows/main.py";
        if(!fs::exists(script)) script=folder/"launcher/windows/main.py";
        if(!fs::exists(script)) throw std::runtime_error("Keep this launcher in the project's build folder, beside the launcher/windows source folder.");
        int argc=0; LPWSTR* argv=CommandLineToArgvW(GetCommandLineW(),&argc);
        if(!argv) throw std::runtime_error("Cannot read launcher arguments.");
        bool check=false; auto interpreter=python(folder);
        std::wstring command=quote(interpreter.wstring())+L" -u "+quote(script.wstring())+L" --build-dir "+quote(folder.wstring());
        for(int i=1;i<argc;++i) { command+=L" "+quote(argv[i]); if(std::wstring(argv[i])==L"--check") check=true; }
        LocalFree(argv);
        SECURITY_ATTRIBUTES sa{sizeof(sa),nullptr,TRUE};
        HANDLE log=CreateFileW((folder/L"launcher.log").c_str(),GENERIC_WRITE,FILE_SHARE_READ,&sa,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
        HANDLE input=CreateFileW(L"NUL",GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,&sa,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        if(log==INVALID_HANDLE_VALUE || input==INVALID_HANDLE_VALUE) {
            if(log!=INVALID_HANDLE_VALUE) CloseHandle(log); if(input!=INVALID_HANDLE_VALUE) CloseHandle(input);
            throw std::runtime_error("Cannot write launcher.log beside the launcher.");
        }
        STARTUPINFOW startup{}; startup.cb=sizeof(startup); startup.dwFlags=STARTF_USESTDHANDLES;
        startup.hStdInput=input; startup.hStdOutput=log; startup.hStdError=log;
        PROCESS_INFORMATION process{};
        bool ok=CreateProcessW(interpreter.c_str(),command.data(),nullptr,nullptr,TRUE,CREATE_NO_WINDOW,nullptr,folder.c_str(),&startup,&process);
        CloseHandle(log); CloseHandle(input);
        if(!ok) throw std::runtime_error("Cannot start Python. See launcher.log.");
        CloseHandle(process.hThread);
        // Report early startup failures, then release the bootstrap executable
        // so Build/Rebuild can update it while the Python window stays open.
        if(WaitForSingleObject(process.hProcess,check ? INFINITE : 2500)==WAIT_TIMEOUT) {
            CloseHandle(process.hProcess); return 0;
        }
        DWORD result=1;
        GetExitCodeProcess(process.hProcess,&result); CloseHandle(process.hProcess);
        if(result && !check) MessageBoxW(nullptr,L"Ultimate Launcher stopped with an error. Read launcher.log beside this executable. Python needs Tcl/Tk installed.",L"Ultimate Launcher",MB_OK|MB_ICONERROR);
        return static_cast<int>(result);
    } catch(const std::exception& error) {
        MessageBoxA(nullptr,error.what(),"Ultimate Launcher",MB_OK|MB_ICONERROR); return 1;
    }
}
