/*
 * This file is a part of ninfs.
 *
 * Copyright (c) 2017-2020 Ian Burgwin
 * This file is licensed under The MIT License (MIT).
 * You can find the full license text in LICENSE.md in the root of this project.
 */

#include <Python.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <inttypes.h>

extern "C" {
#include "aes.h"
}

#if defined _WIN16 || defined _WIN32 || defined _WIN64
#include <windows.h>
typedef HMODULE DYHandle;
#define PATH_MAX MAX_PATH
#else
#include <limits.h>
#include <dlfcn.h>
#define __ldl__ 1
typedef void* DYHandle;
#define WINAPI
#endif

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;

const static union {
    u16 foo;
    u8 islittle;
} endian = {(u16)0x001};

inline static u64 be64(u64 var) {
    if(endian.islittle) {
        #if defined __clang__ || defined __GNUC__
        var = __builtin_bswap64(var);
        #elif defined _MSC_VER
        var = _byteswap_uint64(var);
        #else
        u64 tmp = var;
        ((u8 *) &var)[7] = ((u8 *) &tmp)[0];
        ((u8 *) &var)[6] = ((u8 *) &tmp)[1];
        ((u8 *) &var)[5] = ((u8 *) &tmp)[2];
        ((u8 *) &var)[4] = ((u8 *) &tmp)[3];
        ((u8 *) &var)[3] = ((u8 *) &tmp)[4];
        ((u8 *) &var)[2] = ((u8 *) &tmp)[5];
        ((u8 *) &var)[1] = ((u8 *) &tmp)[6];
        ((u8 *) &var)[0] = ((u8 *) &tmp)[7];
        #endif
    }
    return var;
}

inline static u64 le64(u64 var) {
    if(!endian.islittle) {
        #if defined __clang__ || defined __GNUC__
        var = __builtin_bswap64(var);
        #elif defined _MSC_VER
        var = _byteswap_uint64(var);
        #else
        //sacrifice code size for possible speed up
        u64 tmp = var;
        ((u8 *) &var)[7] = ((u8 *) &tmp)[0];
        ((u8 *) &var)[6] = ((u8 *) &tmp)[1];
        ((u8 *) &var)[5] = ((u8 *) &tmp)[2];
        ((u8 *) &var)[4] = ((u8 *) &tmp)[3];
        ((u8 *) &var)[3] = ((u8 *) &tmp)[4];
        ((u8 *) &var)[2] = ((u8 *) &tmp)[5];
        ((u8 *) &var)[1] = ((u8 *) &tmp)[6];
        ((u8 *) &var)[0] = ((u8 *) &tmp)[7];
        #endif
    }
    return var;
}

class DynamicHelper {
    DYHandle handle;
public:
    inline bool LoadLib(const char *name) {
        #if defined _WIN16 || defined _WIN32 || defined _WIN64
        int length = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, name, -1, NULL, 0);
        if(!length) return false;
        wchar_t *path = (wchar_t * )calloc(length * sizeof(wchar_t), 1);
        if(!path) return false;
        length = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, name, -1, path, length);
        if(!length) {
            free(path);
            return false;
        }
        handle = LoadLibraryExW(path, NULL, LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
        free(path);
        #elif defined __ldl__
        handle = dlopen(name, RTLD_NOW);
        #endif
        return handle != NULL;
    }
    inline void Unload() {
        if(handle) {
            #if defined _WIN16 || defined _WIN32 || defined _WIN64
            FreeLibrary(handle);
            #elif defined __ldl__
            dlclose(handle);
            #endif
            handle = 0;
        }
    }
    inline void GetFunctionPtr(const char* name, void** ptr) {
        *ptr = NULL;
        #if defined _WIN16 || defined _WIN32 || defined _WIN64
        *ptr = (void*)GetProcAddress(handle, name);
        #elif defined __ldl__
        *ptr = dlsym(handle, name);
        #endif
    }
    static std::string GetPathByAddress(const void* addr) {
        #if defined _WIN16 || defined _WIN32 || defined _WIN64
        DYHandle _handle = 0;
        if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, (LPCWSTR)addr, &_handle))
            return std::string("");
        wchar_t *wpath = (wchar_t * )calloc(PATH_MAX * sizeof(wchar_t), 1);
        if(!wpath) {
            free(wpath);
            return std::string("");
        }
        if(!GetModuleFileNameW(_handle, wpath, PATH_MAX)) {
            free(wpath);
            return std::string("");
        }
        int length = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wpath, PATH_MAX, NULL, 0, NULL, NULL);
        if(!length) {
            free(wpath);
            return std::string("");
        }
        char *path = (char * )calloc(length, 1);
        if(!path) {
            free(wpath);
            return std::string("");
        }
        length = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wpath, PATH_MAX, path, length, NULL, NULL);
        free(wpath);
        if(!length) {
            free(path);
            return std::string("");
        }
        std::string outpath(path);
        free(path);
        auto found = outpath.find_last_of("/\\");
        if(found == std::string::npos) return std::string("");
        return std::string(outpath.substr(0, found + 1));
        #elif defined __ldl__
        Dl_info info;
        if(!dladdr(addr, &info)) return std::string("");
        if(!info.dli_fname) return std::string("");
        char* path = realpath(info.dli_fname, NULL);
        if(!path) return std::string("");
        std::string outpath(path);
        free(path);
        auto found = outpath.find_last_of("/");
        if(found == std::string::npos) return std::string("");
        return std::string(outpath.substr(0, found + 1));
        #else
        return std::string("");
        #endif
    }
    inline bool HasHandle() {return handle != NULL;}
    DynamicHelper() : handle(0) {}
    ~DynamicHelper() {Unload();}
};

typedef struct {
    PyObject_HEAD
    u8 roundkeys_x2[352];
} XTSNObject;

class bigint128 {
public:
    union {
        u8 v8[16];
        u64 v64[2];
    };
};

class SectorOffset : public bigint128 {
public:
    inline u64* Lo() {return &v64[0];}
    inline u64* Hi() {return &v64[1];}
    inline void Step() {
        if (v64[0] > (v64[0] + 1LLU)) v64[1] += 1LLU;
        v64[0] += 1LLU;
    }
    inline void Step(u64 amount) {
        if (v64[0] > (v64[0] + amount)) v64[1] += 1LLU;
        v64[0] += amount;
    }
    static int FromPyLong(PyObject *o, SectorOffset *p) {
        if(!PyLong_CheckExact(o)) {
            PyErr_SetString(PyExc_ValueError, "Not an int was given, convertion to sector offset failed.");
            return 0;
        }
        auto _hi = PyObject_CallMethod(o, "__rshift__", "i", 64);
        if(!_hi) return 0;
        *p->Lo() = PyLong_AsUnsignedLongLongMask(o);
        *p->Hi() = PyLong_AsUnsignedLongLongMask(_hi);
        Py_DECREF(_hi);

        return 1;
    }
};

template<bool (*crypher)(const u8*, const u8*, u8*, void*)>
class Tweak : public bigint128 {
public:
    inline Tweak(SectorOffset& offset, u8 *roundkeys_tweak, void* ctx) {
        v64[1] = be64(offset.v64[0]);
        v64[0] = be64(offset.v64[1]);
        if(!crypher(roundkeys_tweak, v8, v8, ctx)) throw false;
    }
    inline void Update() {
        int flag = v8[15] & 0x80;
        v64[1] = le64(le64(v64[1]) << 1) | (le64(v64[0]) >> 63);
        v64[0] = le64(le64(v64[0]) << 1);
        if (flag) v8[0] ^= 0x87;
    }
};

class Buffer {
public:
    bigint128* ptr;
    u64 len;
    inline Buffer& operator^=(bigint128& tweak) {
        ptr->v64[0] ^= tweak.v64[0];
        ptr->v64[1] ^= tweak.v64[1];
        return *this;
    }
    inline void Step() {
        ptr++;
        len -= 16LLU;
    }
};

void *(WINAPI *EVP_CIPHER_CTX_new)() = NULL;
void *(WINAPI *EVP_aes_128_ecb)() = NULL;
int (WINAPI *EVP_CipherInit_ex)(void*, void*, void*, const void*, void*, int) = NULL;
int (WINAPI *EVP_CIPHER_CTX_key_length)(void*) = NULL;
void (WINAPI *EVP_CIPHER_CTX_set_padding)(void*, int) = NULL;
int (WINAPI *EVP_CipherUpdate)(void*, void*, int*, const void*, int) = NULL;
int (WINAPI *EVP_CipherFinal_ex)(void*, void*, int*) = NULL;
void (WINAPI *EVP_CIPHER_CTX_free)(void*) = NULL;
unsigned long (WINAPI *OpenSSL_version_num)() = NULL;

static DynamicHelper lcrypto;
static bool lib_to_load = true;

template<bool encrypt>
bool openssl_crypt(const u8* key, const u8* data, u8* out, void *ctx) {
    if(!ctx) return false;
    bool ret = false;
    do {
        if(!EVP_CipherInit_ex(ctx, EVP_aes_128_ecb(), NULL, key, NULL, (int)encrypt)) break;
        if(EVP_CIPHER_CTX_key_length(ctx) != 16) break;
        EVP_CIPHER_CTX_set_padding(ctx, 0);
        int foo;
        if(!EVP_CipherUpdate(ctx, out, &foo, data, 16)) break;
        if(!EVP_CipherFinal_ex(ctx, out + foo, &foo)) break;
        ret = true;
    } while(0);
    return ret;
}

bool aes_decrypt_128_wrap(const u8* roundkey, const u8* data, u8* out, void *ctx) {
    (void)ctx; //warning suppress
    aes_decrypt_128(roundkey, data, out);
    return true;
}

bool aes_encrypt_128_wrap(const u8* roundkey, const u8* data, u8* out, void *ctx) {
    (void)ctx; //warning suppress
    aes_encrypt_128(roundkey, data, out);
    return true;
}

template<bool (*crypher)(const u8*, const u8*, u8*, void*), bool (*crypher2)(const u8*, const u8*, u8*, void*), bool ossl>
class XTSN {
    SectorOffset sectoroffset;
    Buffer buf;
    u64 sector_size;
    u64 skipped_bytes;
    u8 *roundkeys_key;
    u8 *roundkeys_tweak;
    void* ctx;
    #ifdef DEBUGON
    void Debug() { //debug printing.
        PySys_WriteStdout("Sector Offset (Lo, Hi): %llu, %llu\n"
            "Buffer Length: %llu\n"
            "Sector Size: %llu\n"
            "Skipped Bytes: %llu\n\n",
            (unsigned long long)*sectoroffset.Lo(), (unsigned long long)*sectoroffset.Hi(),
            (unsigned long long)buf.len,
            (unsigned long long)sector_size,
            (unsigned long long)skipped_bytes);
        fflush(stdout);
    }
    #endif
    void Run() {
        if(skipped_bytes) {
            if(skipped_bytes / sector_size) {
                sectoroffset.Step(skipped_bytes / sector_size);
                skipped_bytes %= sector_size;
            }
            if(skipped_bytes) {
                Tweak<crypher2> tweak(sectoroffset, roundkeys_tweak, ctx);
                u64 i;
                for (i = 0; i < (skipped_bytes / 16LLU); i++) {
                    tweak.Update();
                }
                for (i = 0; i < ((sector_size - skipped_bytes) / 16LLU) && buf.len; i++) {
                    buf ^= tweak;
                    crypher(roundkeys_key, buf.ptr->v8, buf.ptr->v8, ctx);
                    buf ^= tweak;
                    tweak.Update();
                    buf.Step();
                }
                sectoroffset.Step();
            }
        }
        while(buf.len) {
            Tweak<crypher2> tweak(sectoroffset, roundkeys_tweak, ctx);
            u64 i;
            for (i = 0; i < (sector_size / 16LLU) && buf.len; i++) {
                buf ^= tweak;
                crypher(roundkeys_key, buf.ptr->v8, buf.ptr->v8, ctx);
                buf ^= tweak;
                tweak.Update();
                buf.Step();
            }
            sectoroffset.Step();
        }
    }
public:
    inline PyObject *PythonRun(XTSNObject *self, PyObject *args, PyObject *kwds) {
        Py_buffer orig_buf;
        PyObject *local_buf = NULL;

        static const char* keywords[] = {
            "buf",
            "sector_off",
            "sector_size",
            "skipped_bytes",
            NULL,
        };

        if (!PyArg_ParseTupleAndKeywords(args, kwds, "y*O&|KK", (char**)keywords, &orig_buf,
           &SectorOffset::FromPyLong, &sectoroffset, &sector_size, &skipped_bytes))
            return NULL;

        if (orig_buf.len == 0) { //nothing to crypt i guess
            local_buf = PyBytes_FromStringAndSize((char * ) NULL, 0);
            if (!local_buf) {
                PyErr_SetString(PyExc_MemoryError, "Python doesn't have memory for the buffer.");
            }
            goto end;
        }

        if (orig_buf.len % 16) {
            PyErr_SetString(PyExc_ValueError, "length not divisable by 16");
            goto end;
        }

        if (skipped_bytes % 16) {
            PyErr_SetString(PyExc_ValueError, "skipped bytes not divisable by 16");
            goto end;
        }

        if (sector_size % 16 || sector_size == 0) {
            PyErr_SetString(PyExc_ValueError, sector_size == 0 ? "sector size must not be 0" : "sector size not divisable by 16");
            goto end;
        }

        local_buf = PyBytes_FromStringAndSize((char * ) orig_buf.buf, orig_buf.len);

        if (!local_buf) {
            PyErr_SetString(PyExc_MemoryError, "Python doesn't have memory for the buffer.");
            goto end;
        }

        roundkeys_key = self->roundkeys_x2;
        roundkeys_tweak = self->roundkeys_x2 + 0xB0;
        buf.ptr = (bigint128 *) PyBytes_AsString(local_buf);
        buf.len = (u64) orig_buf.len;

        #ifdef DEBUGON
        Debug();
        #endif
        try {
            if(ossl) ctx = EVP_CIPHER_CTX_new();
            else ctx = NULL;
            Run();
        } catch(...) {
            Py_XDECREF(local_buf);
            local_buf = NULL;
            PyErr_SetString(PyExc_RuntimeError, "Unexpected error from openssl.");
        }

        if(ossl) EVP_CIPHER_CTX_free(ctx);

    end:
        PyBuffer_Release(&orig_buf);
        return local_buf;
    }
    inline XTSN() : sector_size(0x200), skipped_bytes(0) {}
};

typedef XTSN<&aes_decrypt_128_wrap, aes_encrypt_128_wrap, false> XTSNDecrypt;
typedef XTSN<&aes_encrypt_128_wrap, aes_encrypt_128_wrap, false> XTSNEncrypt;
typedef XTSN<&openssl_crypt<false>, &openssl_crypt<true>, true> XTSNOpenSSLDecrypt;
typedef XTSN<&openssl_crypt<true>, &openssl_crypt<true>, true> XTSNOpenSSLEncrypt;

inline static void
aes_xtsn_schedule_128(u8* key, u8* tweakin, u8* roundkeys_x2) {
    aes_key_schedule_128(key, roundkeys_x2);
    aes_key_schedule_128(tweakin, roundkeys_x2 + 0xB0);
}

// python stuff
static int XTSN_init(XTSNObject *self, PyObject *args, PyObject *kwds) {
    Py_buffer key, tweak;
    int ret = -1;

    static const char* keywords[] = {
        "crypt",
        "tweak",
        NULL,
    };

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "y*y*", (char**)keywords, &key, &tweak)) {
        return -1;
    }

    if (key.len != 16) {
        PyErr_SetString(PyExc_ValueError, "key len is not 16");
        goto end;
    }

    if (tweak.len != 16) {
        PyErr_SetString(PyExc_ValueError, "tweak len is not 16");
        goto end;
    }

    aes_xtsn_schedule_128((u8*)key.buf, (u8*)tweak.buf, self->roundkeys_x2);
    ret = 0;

end:
    PyBuffer_Release(&key);
    PyBuffer_Release(&tweak);
    return ret;
}

static PyObject *py_xtsn_decrypt(XTSNObject *self, PyObject *args, PyObject *kwds) {
    XTSNDecrypt xtsn;
    return xtsn.PythonRun(self, args, kwds);
}

static PyObject *py_xtsn_encrypt(XTSNObject *self, PyObject *args, PyObject *kwds) {
    XTSNEncrypt xtsn;
    return xtsn.PythonRun(self, args, kwds);
}

static PyObject *py_xtsn_openssl_decrypt(XTSNObject *self, PyObject *args, PyObject *kwds) {
    XTSNOpenSSLDecrypt xtsn;
    return xtsn.PythonRun(self, args, kwds);
}

static PyObject *py_xtsn_openssl_encrypt(XTSNObject *self, PyObject *args, PyObject *kwds) {
    XTSNOpenSSLEncrypt xtsn;
    return xtsn.PythonRun(self, args, kwds);
}

static PyMethodDef XTSN_methods[] = {
    {"decrypt", (PyCFunction) py_xtsn_decrypt, METH_VARARGS | METH_KEYWORDS, "Decrypt AES-XTSN content."},
    {"encrypt", (PyCFunction) py_xtsn_encrypt, METH_VARARGS | METH_KEYWORDS, "Encrypt AES-XTSN content."},
    {NULL}
};

static class XTSNType_PyTypeObject : public PyTypeObject {
public:
    XTSNType_PyTypeObject() : PyTypeObject({PyVarObject_HEAD_INIT(NULL, 0)}) {
        tp_name = "crypto.XTSN";
        tp_basicsize = sizeof(XTSNObject);
        tp_itemsize = 0;
        tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE;
        tp_doc = "Nintendo AES-XTSN";
        tp_methods = XTSN_methods;
        tp_init = (initproc) XTSN_init;
        tp_new = PyType_GenericNew;
    }
} XTSNType;

static void unload_lcrypto(void* unused) {
    (void)unused;
    if(!lib_to_load) {
        XTSN_methods[0].ml_meth = (PyCFunction)py_xtsn_decrypt;
        XTSN_methods[1].ml_meth = (PyCFunction)py_xtsn_encrypt;
        lcrypto.Unload();
        lib_to_load = true;
    }
}

static void load_lcrypto() {
    if(!lib_to_load) return;
    static std::recursive_mutex loadlock;
    #if (defined _WIN16 || defined _WIN32) && !defined _WIN64
    static const char* const names[] = {
        "libcrypto-1_1.dll", "libcrypto.dll"
    };
    #elif defined _WIN64
    static const char* const names[] = {
        "libcrypto-1_1-x64.dll", "libcrypto-x64.dll", "libcrypto-1_1.dll", "libcrypto.dll"
    };
    #elif defined __APPLE__ && defined __MACH__
    static const char* const names[] = {
        "libcrypto.1.1.dylib", "libcrypto.dylib"
    };
    #elif defined __ldl__
    static const char* const names[] = {
        "libcrypto.so", "libcrypto.so.1.1", "libcrypto.so.111"
    };
    #else
    static const char* const names[] = {};
    #endif
    try {loadlock.lock();} catch(...) {return;}
    if(!lib_to_load) {
        loadlock.unlock();
        return;
    }
    bool found = false;
    try {
        std::string *paths[2] = {nullptr, nullptr};
        std::string modulepath("");
        try {
            modulepath = DynamicHelper::GetPathByAddress((const void * )&load_lcrypto);
            paths[0] = &modulepath;
        } catch(...) {}
        for(size_t i = 0; !found && i < (sizeof(paths) / sizeof(paths[0])); i++) {
            try {
                for(size_t j = 0; !found && j < (sizeof(names) / sizeof(names[0])); j++) {
                    if(paths[i]) {
                        if(!lcrypto.LoadLib((*paths[i] + names[j]).c_str())) continue;
                    } else {
                        if(!lcrypto.LoadLib(names[j])) continue;
                    }
                    lcrypto.GetFunctionPtr("EVP_CIPHER_CTX_new", (void**)&EVP_CIPHER_CTX_new);
                    lcrypto.GetFunctionPtr("EVP_aes_128_ecb", (void**)&EVP_aes_128_ecb);
                    lcrypto.GetFunctionPtr("EVP_CipherInit_ex", (void**)&EVP_CipherInit_ex);
                    lcrypto.GetFunctionPtr("EVP_CIPHER_CTX_key_length", (void**)&EVP_CIPHER_CTX_key_length);
                    lcrypto.GetFunctionPtr("EVP_CIPHER_CTX_set_padding", (void**)&EVP_CIPHER_CTX_set_padding);
                    lcrypto.GetFunctionPtr("EVP_CipherUpdate", (void**)&EVP_CipherUpdate);
                    lcrypto.GetFunctionPtr("EVP_CipherFinal_ex", (void**)&EVP_CipherFinal_ex);
                    lcrypto.GetFunctionPtr("EVP_CIPHER_CTX_free", (void**)&EVP_CIPHER_CTX_free);
                    lcrypto.GetFunctionPtr("OpenSSL_version_num", (void**)&OpenSSL_version_num);

                    if(!EVP_CIPHER_CTX_new || !EVP_aes_128_ecb || !EVP_CipherInit_ex ||
                      !EVP_CIPHER_CTX_key_length || !EVP_CIPHER_CTX_set_padding ||
                      !EVP_CipherUpdate || !EVP_CIPHER_CTX_free || !EVP_CIPHER_CTX_free ||
                      !OpenSSL_version_num) {
                        lcrypto.Unload();
                        continue;
                    }

                    //check at bare minimum, 1.1, any variant
                    if(OpenSSL_version_num() < 0x10100000LU) {
                        lcrypto.Unload();
                        PySys_WriteStderr("[HAC] Found openssl lib, but below version 1.1.\n      Not using\n");
                        continue;
                    }
                    found = true;
                }
            } catch(...) {
                lcrypto.Unload();
            }
        }
    } catch(...) {}

    if(found) {
        XTSN_methods[0].ml_meth = (PyCFunction)py_xtsn_openssl_decrypt;
        XTSN_methods[1].ml_meth = (PyCFunction)py_xtsn_openssl_encrypt;
        PySys_WriteStdout("[HAC] Found and using openssl lib.\n");
        lib_to_load = false;
    }
    loadlock.unlock();
}

static struct PyModuleDef _crypto_module = {
    PyModuleDef_HEAD_INIT,
    "_crypto",
    NULL,
    -1,
    NULL,
    NULL,
    NULL,
    NULL,
    unload_lcrypto,
};

PyMODINIT_FUNC PyInit__crypto(void) {
    load_lcrypto();
    PyObject *m;
    if (PyType_Ready(&XTSNType) < 0)
        return NULL;

    m = PyModule_Create(&_crypto_module);
    if (m == NULL)
        return NULL;

    Py_INCREF(&XTSNType);
    PyModule_AddObject(m, "XTSN", (PyObject *) &XTSNType);
    return m;
}
