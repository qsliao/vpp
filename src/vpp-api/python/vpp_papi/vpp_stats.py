#!/usr/bin/env python

from __future__ import print_function
from cffi import FFI

ffi = FFI()
ffi.cdef("""
typedef uint64_t counter_t;
typedef struct {
  counter_t packets;
  counter_t bytes;
} vlib_counter_t;

typedef enum {
  STAT_DIR_TYPE_ILLEGAL = 0,
  STAT_DIR_TYPE_SCALAR_POINTER,
  STAT_DIR_TYPE_VECTOR_POINTER,
  STAT_DIR_TYPE_COUNTER_VECTOR_SIMPLE,
  STAT_DIR_TYPE_COUNTER_VECTOR_COMBINED,
  STAT_DIR_TYPE_ERROR_INDEX,
  STAT_DIR_TYPE_SERIALIZED_NODES,
} stat_directory_type_t;

typedef struct {
  stat_directory_type_t type;
  void *value;
} stat_segment_directory_entry_t;

typedef struct {
  char *name;
  stat_directory_type_t type;
  union {
    double scalar_value;
    uint64_t error_value;
    uint64_t *vector_pointer;
    counter_t **simple_counter_vec;
    vlib_counter_t **combined_counter_vec;
  };
} stat_segment_data_t;

typedef struct {
  char *name;
  stat_segment_directory_entry_t *ep;
} stat_segment_cached_pointer_t;

int stat_segment_connect (char *socket_name);
void stat_segment_disconnect (void);

uint8_t  **stat_segment_ls (uint8_t **pattern);
stat_segment_data_t *stat_segment_dump (uint8_t ** counter_vec);
/* Collects registered counters */
stat_segment_cached_pointer_t *stat_segment_register (uint8_t ** counter_vec);
stat_segment_data_t *stat_segment_collect (stat_segment_cached_pointer_t *);
void stat_segment_data_free (stat_segment_data_t * res);
double stat_segment_heartbeat (void);
int stat_segment_vec_len(void *vec);
uint8_t **stat_segment_string_vector(uint8_t **string_vector, char *string);
""")


# Utility functions
def make_string_vector(api, strings):
    vec = ffi.NULL
    if type(strings) is not list:
        strings = [strings]
    for s in strings:
        vec = api.stat_segment_string_vector(vec, ffi.new("char []", s))
    return vec


def make_string_list(api, vec):
    vec_len = api.stat_segment_vec_len(vec)
    return [ffi.string(vec[i]) for i in range(vec_len)]


# 2-dimensonal array of thread, index
def simple_counter_vec_list(api, e):
    vec = []
    for thread in range(api.stat_segment_vec_len(e)):
        len_interfaces = api.stat_segment_vec_len(e[thread])
        if_per_thread = [e[thread][interfaces]
                         for interfaces in range(len_interfaces)]
        vec.append(if_per_thread)
    return vec


def vlib_counter_dict(c):
    return {'packets': c.packets,
            'bytes': c.bytes}


def combined_counter_vec_list(api, e):
    vec = []
    for thread in range(api.stat_segment_vec_len(e)):
        len_interfaces = api.stat_segment_vec_len(e[thread])
        if_per_thread = [vlib_counter_dict(e[thread][interfaces])
                         for interfaces in range(len_interfaces)]
        vec.append(if_per_thread)
    return vec


def stat_entry_to_python(api, e):
    if e.type == 3:
        return simple_counter_vec_list(e.simple_counter_vec)
    if e.type == 4:
        return combined_counter_vec_list(api, e.combined_counter_vec)
    if e.type == 5:
        return e.error_value
    return None


class VPPStats:
    def __init__(self, socketname='/var/run/stats.sock'):
        self.api = ffi.dlopen('libvppapiclient.so')
        rv = self.api.stat_segment_connect(socketname)
        if rv != 0:
            raise IOError()

    def heartbeat(self):
        return self.api.stat_segment_heartbeat()

    def ls(self, patterns):
        return self.api.stat_segment_ls(make_string_vector(self.api, patterns))

    def dump(self, counters):
        stats = {}
        rv = self.api.stat_segment_dump(counters)
        rv_len = self.api.stat_segment_vec_len(rv)
        for i in range(rv_len):
            n = ffi.string(rv[i].name)
            e = stat_entry_to_python(self.api, rv[i])
            if e:
                stats[n] = e
        return stats

    def dump_str(self, counters_str):
        return self.dump(make_string_vector(self.api, counters_str))

    def disconnect(self):
        self.api.stat_segment_disconnect()

    def set_errors(self):
        '''Return all errors counters > 0'''
        error_names = self.ls(['/err/'])
        error_counters = self.dump(error_names)
        return {k: error_counters[k]
                for k in error_counters.keys() if error_counters[k]}

    def set_errors_str(self):
        '''Return all errors counters > 0 pretty printed'''
        s = 'ERRORS:\n'
        error_counters = self.set_errors()
        for k in sorted(error_counters):
            s += '{:<60}{:>10}\n'.format(k, error_counters[k])
        return s

    def register(self):
        raise NotImplemented

    def collect(self):
        raise NotImplemented
