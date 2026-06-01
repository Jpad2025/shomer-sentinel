/**
 * Shomer Sentinel — fetch con sesión (Bearer + cookie access_token).
 * Content-Type application/json solo si hay body y no es FormData/Blob (GET/POST sin body quedan limpios).
 */
(function () {
  'use strict';

  function shomerAuthHeaders() {
    var token = localStorage.getItem('auth_token') || '';
    var h = {};
    if (token) h['Authorization'] = 'Bearer ' + token;
    return h;
  }

  function shomerFetch(url, opts) {
    opts = opts || {};
    opts.credentials = opts.credentials || 'include';
    var merged = Object.assign({}, shomerAuthHeaders(), opts.headers || {});
    var b = opts.body;
    if (b !== undefined && b !== null) {
      var isForm = typeof FormData !== 'undefined' && b instanceof FormData;
      var isBlob = typeof Blob !== 'undefined' && b instanceof Blob;
      if (!isForm && !isBlob && !merged['Content-Type'] && !merged['content-type']) {
        merged['Content-Type'] = 'application/json';
      }
    }
    opts.headers = merged;
    return fetch(url, opts);
  }

  window.shomerAuthHeaders = shomerAuthHeaders;
  window.shomerFetch = shomerFetch;
  window._authHeaders = shomerAuthHeaders;
  window._authFetch = shomerFetch;
})();
