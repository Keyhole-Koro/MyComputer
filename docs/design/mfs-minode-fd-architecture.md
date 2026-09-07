# Design Doc: MyFileSystem (MFS) Inodes (`minode`) & File Descriptors (`mfd`) (FS-002)

**Version:** 3.1  
**Target:** `MyComputer` (32-bit RISC / MyKernel / MyOS)  
**Author:** Antigravity & MyComputer Engineering  

---

## 1. Overview

This document specifies the architecture for **In-Memory Inodes (`minode`)**, **File Descriptors (`mfd`)**, and **Path Resolution** built directly on top of **MyFileSystem (MFS)** and the SSD storage device.

### Design Goals:
1. **Direct & Fast:** Direct mapping between user file descriptors, memory inodes, and MFS disk blocks without any abstraction layers.
2. **Unified Descriptors (`mfd` 0–7):** Standard input/output (`stdin`, `stdout`, `stderr`) and disk files share a single, consistent descriptor table.
3. **In-Memory Inode Cache (`minode`):** Keeps active file metadata in RAM to minimize SSD block reads and ensure fast lookups.
4. **Hierarchical Paths:** Supports path resolution (e.g., `"/docs/readme.txt"`) directly across MFS directory blocks.

---

## 2. Subsystem Constraints & Invariants

| Subsystem | Constant / Field | Constraint / Invariant | Purpose / Rationale |
|---|---|---|---|
| **Storage Geometry** | `BLOCK_SIZE = 65536` | Fixed 64 KiB block transfers | Matches hardware SSD memory-mapped block register |
| **Storage Geometry** | `PAYLOAD = 65532` | 4-byte next-block pointer header at byte 0..3 | Singly-linked block chains on disk (0 = EOF) |
| **Storage Geometry** | `NAME_MAX = 16` | 15 printable ASCII characters + 1 null terminator | Fixed 32-byte directory entry record |
| **Storage Geometry** | `MAX_FILES = 2048` | Maximum 2,048 files system-wide | Fits exactly in 1 single 64 KiB entry table block |
| **Inode Cache** | `MINODE_CACHE_MAX = 16` | Maximum 16 active in-memory cached inodes | Bounds kernel heap usage |
| **Inode Cache** | `ref_count` | Slot evicted only when `ref_count == 0` | Prevents invalidating open file handles |
| **Inode Cache** | `is_dirty` | Flushed to disk before eviction or on last close | Guarantees metadata durability on SSD |
| **File Descriptors** | `FD_MAX = 8` | Maximum 8 simultaneous open descriptors | Fits in fixed kernel array |
| **File Descriptors** | `mfd = 0, 1, 2` | Permanently reserved for `stdin`, `stdout`, `stderr` | Fixed standard streams mapped to `serial.mln` |
| **File Descriptors** | `mfd = 3..7` | User files allocated dynamically | Ensures descriptors 0..2 are never closed |
| **Concurrency** | `g_buf` | Single shared 64 KiB kernel buffer | File operations are synchronous and non-reentrant |

---

## 3. System Architecture

```
[ User Application / Process ]
┌─────────────────────────────────────────────────────────────┐
│  File Descriptors (mfd: 0, 1, 2, 3, ...)                    │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
         mfd == 0, 1, 2                  mfd >= 3
    (stdin / stdout / stderr)          (MFS Disk Files)
               │                               │
               ▼                               ▼
     ┌──────────────────┐           ┌────────────────────────┐
     │  Serial / TTY    │           │ Open File Table        │
     │  (serial.mln)    │           │ (mfile_t g_mfile[8])   │
     └──────────────────┘           └──────────┬─────────────┘
                                               │
                                               ▼
                                    ┌────────────────────────┐
                                    │ In-Memory Inode Cache  │
                                    │ (minode_t g_minode[16])│
                                    └──────────┬─────────────┘
                                               │
                                               ▼
                                    ┌────────────────────────┐
                                    │ MFS Disk Engine        │
                                    │ (SSD Block Driver)     │
                                    └────────────────────────┘
```

---

## 4. Data Structures (MyLang `.mln`)

### 4.1 `minode` (In-Memory Inode)

The `minode` represents an active file or directory entry cached in RAM. It mirrors the 32-byte on-disk entry from MFS block 1, supplemented with runtime reference tracking and dirty flags:

```c
// File Types
i32 MINODE_UNUSED    = 0;
i32 MINODE_FILE      = 1;
i32 MINODE_DIR       = 2;

i32 MINODE_CACHE_MAX = 16;

typedef struct {
    i32 entry_idx;      // On-disk entry index in MFS Entry Block (0..2047)
    i32 type;           // MINODE_FILE or MINODE_DIR
    i32 first_block;    // First data block index on SSD
    i32 size;           // File size in bytes
    char name[16];      // Null-terminated filename (up to 15 chars)
    
    // In-Memory Tracking
    i32 ref_count;      // Number of open handles pointing to this inode
    i32 is_dirty;       // 1 = metadata changed (needs disk sync), 0 = clean
} minode_t;

minode_t g_minode_table[16];
```

---

### 4.2 `mfile` (Open File Description)

Tracks an active open file session (current read/write cursor and access flags):

```c
i32 FD_TYPE_UNUSED = 0;
i32 FD_TYPE_SERIAL = 1; // stdin / stdout / stderr
i32 FD_TYPE_FILE   = 2; // MFS disk file

i32 MFD_MAX = 8; // Maximum simultaneous open descriptors

typedef struct {
    i32 type;          // FD_TYPE_SERIAL or FD_TYPE_FILE
    i32 minode_idx;    // Index into g_minode_table (-1 if SERIAL)
    i32 offset;        // Current byte position for read/write
    i32 flags;         // 1 = O_RDONLY, 2 = O_WRONLY, 3 = O_RDWR, 4 = O_APPEND
} mfile_t;

mfile_t g_mfile_table[8];
```

---

### 4.3 Default Standard Descriptors

At boot, the first three slots in `g_mfile_table` are reserved for standard I/O:

| `mfd` | Name | Type | Target Device |
|---|---|---|---|
| `0` | `stdin` | `FD_TYPE_SERIAL` | Serial Port In (`serial.read_byte()`) |
| `1` | `stdout` | `FD_TYPE_SERIAL` | Serial Port Out (`serial.write_byte()`) |
| `2` | `stderr` | `FD_TYPE_SERIAL` | Serial Port Out / Debug Console |
| `3..7`| User files | `FD_TYPE_FILE` | Dynamically assigned to open MFS files |

---

## 5. Path Resolution (`path_clean_name` / `mfs_lookup_path`)

Paths are resolved by stripping leading `/` delimiters and sanitizing filenames to match on-disk entries:

```
Input: "/docs/readme.txt" or "/readme.txt"
  │
  ├─ 1. Strip leading '/'
  ├─ 2. Truncate to NAME_MAX - 1 (15 characters)
  └─ 3. Search MFS Block 1 for matching filename -> return minode_get(entry_idx)
```

---

## 6. System Call Operations

### 6.1 `sys_open(char *path, i32 flags)`
1. Sanitize `path` via `path_clean_name(path)` $\rightarrow$ search entry in Block 1.
2. If not found, return `-1`.
3. Allocate lowest free slot in `g_fd_table` (starting from `mfd = 3`).
4. Acquire in-memory inode: `minode_idx = minode_get(entry_idx)`.
5. Initialize `g_fd_table[mfd]` (`type = FD_TYPE_FILE`, `offset = 0`).
6. Return `mfd`.

---

### 6.2 `sys_read(i32 mfd, i32 buf_addr, i32 count)`
* **`mfd == 0` (stdin):** Non-blocking read from `serial.read_input()`.
* **`mfd >= 3` (file):** Reads up to `count` bytes from MFS block chain, updating `offset`.

---

### 6.3 `sys_write(i32 mfd, i32 buf_addr, i32 count)`
* **`mfd == 1, 2` (stdout/stderr):** Writes bytes directly to `serial.putc()`.
* **`mfd >= 3` (file):** Appends/overwrites data blocks on SSD, marks `is_dirty = 1`, syncs new size.

---

### 6.4 `sys_seek(i32 mfd, i32 offset, i32 whence)`
* Adjusts `g_fd_table[mfd].offset` based on `SEEK_SET (0)`, `SEEK_CUR (1)`, or `SEEK_END (2)`.

---

### 6.5 `sys_close(i32 mfd)`
* If `mfd < 3`, no-op (preserves standard streams).
* If `mfd >= 3`, calls `minode_put(minode_idx)` and marks slot `FD_TYPE_UNUSED`.
