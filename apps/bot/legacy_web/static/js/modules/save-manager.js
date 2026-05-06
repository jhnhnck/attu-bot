/**
 * Save Manager Module
 * Provides dirty tracking, floating save button, field-level validation errors,
 * and navigation guards for config pages.
 */

/**
 * Initialize a save manager for a config form.
 *
 * @param {object} opts
 * @param {string} opts.formId - ID of the <form> element
 * @param {function} opts.save - async (data) => response; called on save click
 * @param {function} [opts.serialize] - optional custom serializer; defaults to serializeForm
 * @returns {{ isDirty: () => boolean, reset: () => void, destroy: () => void }}
 */
export function initSaveManager({ formId, save, serialize }) {
    const form = document.getElementById(formId);
    if (!form) {
        console.warn(`save-manager: form #${formId} not found`);
        return { isDirty: () => false, reset: () => {}, destroy: () => {} };
    }

    // ---- state ----
    let snapshot = _snapshot(form, serialize);
    let dirty = false;
    let saving = false;
    let pendingHref = null;

    // ---- floating save button ----
    const fab = document.createElement('button');
    fab.type = 'button';
    fab.className = 'btn btn-primary btn-lg save-fab hidden';
    fab.innerHTML = '<i data-feather="save" style="width:18px;height:18px" class="me-1"></i> Save';
    document.body.appendChild(fab);
    if (typeof feather !== 'undefined') {feather.replace();}

    // ---- dirty tracking ----
    function check() {
        const current = _snapshot(form, serialize);
        const nowDirty = current !== snapshot;
        if (nowDirty !== dirty) {
            dirty = nowDirty;
            fab.classList.toggle('hidden', !dirty);
            if (dirty) {
                window.onbeforeunload = () => '';
            } else {
                window.onbeforeunload = null;
            }
        }
    }

    form.addEventListener('input', check);
    form.addEventListener('change', check);

    // also watch MutationObserver for hidden fields updated externally (list fields, emoji map)
    const observer = new MutationObserver(() => requestAnimationFrame(check));
    form.querySelectorAll('input[type="hidden"]').forEach(el => {
        observer.observe(el, { attributes: true, attributeFilter: ['value'] });
    });

    // ---- save flow ----
    async function doSave() {
        if (saving) {return;}
        saving = true;
        fab.disabled = true;
        fab.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> Saving...';

        try {
            _clearErrors(form);
            const data = serialize ? serialize(form) : _defaultSerialize(form);
            await save(data);

            // success: update snapshot, mark clean, show toast
            snapshot = _snapshot(form, serialize);
            dirty = false;
            fab.classList.add('hidden');
            window.onbeforeunload = null;
            _toast('Changes saved', 'success');
        } catch (err) {
            if (err.status === 400 && err.fields) {
                _showFieldErrors(form, err.fields);
            }
            _toast(err.message || 'Save failed', 'danger');
        } finally {
            saving = false;
            fab.disabled = false;
            fab.innerHTML = '<i data-feather="save" style="width:18px;height:18px" class="me-1"></i> Save';
            if (typeof feather !== 'undefined') {feather.replace();}
        }
    }

    fab.addEventListener('click', doSave);

    // ---- navigation guard ----
    const unsavedModal = document.getElementById('unsavedModal');
    const discardBtn = document.getElementById('unsaved-discard-btn');

    function interceptNav(e) {
        if (!dirty) {return;}

        const link = e.target.closest('a[href]');
        if (!link) {return;}
        const href = link.getAttribute('href');
        if (!href || href === '#' || href.startsWith('javascript:')) {return;}

        e.preventDefault();
        pendingHref = href;

        if (unsavedModal) {
            const modal = new bootstrap.Modal(unsavedModal);
            modal.show();
        } else {
            // fallback: just navigate
            window.location.href = href;
        }
    }

    // intercept sidebar and guild toggle navigation
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {sidebar.addEventListener('click', interceptNav);}

    if (discardBtn) {
        discardBtn.addEventListener('click', () => {
            window.onbeforeunload = null;
            if (pendingHref) {
                window.location.href = pendingHref;
            }
        });
    }

    // ---- public API ----
    function reset() {
        snapshot = _snapshot(form, serialize);
        dirty = false;
        fab.classList.add('hidden');
        window.onbeforeunload = null;
    }

    function destroy() {
        form.removeEventListener('input', check);
        form.removeEventListener('change', check);
        observer.disconnect();
        fab.remove();
        window.onbeforeunload = null;
        if (sidebar) {sidebar.removeEventListener('click', interceptNav);}
    }

    return { isDirty: () => dirty, reset, destroy };
}

// ---- internals ----

function _snapshot(form, serialize) {
    if (serialize) {
        try {
            return JSON.stringify(serialize(form));
        } catch {
            // fall through to default
        }
    }
    return _defaultSnapshot(form);
}

function _defaultSnapshot(form) {
    const parts = [];
    for (const el of form.elements) {
        if (!el.name) {continue;}
        if (el.type === 'checkbox') {
            parts.push(`${el.name}=${el.checked}`);
        } else {
            parts.push(`${el.name}=${el.value}`);
        }
    }
    return parts.join('&');
}

function _defaultSerialize(form) {
    const data = {};
    for (const el of form.elements) {
        if (!el.name) {continue;}
        if (el.type === 'checkbox') {
            data[el.name] = el.checked;
        } else {
            data[el.name] = el.value;
        }
    }
    return data;
}

function _clearErrors(form) {
    form.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));
    form.querySelectorAll('.save-error-indicator').forEach(el => el.remove());
    form.querySelectorAll('.invalid-feedback[data-save-error]').forEach(el => el.remove());
}

function _showFieldErrors(form, fields) {
    for (const [path, msg] of Object.entries(fields)) {
        // try to find input by name (exact or dotted)
        const input = form.querySelector(`[name="${path}"]`) || form.querySelector(`[name$=".${path}"]`);
        if (!input) {continue;}

        input.classList.add('is-invalid');

        // insert bold red ! before label
        const label = input.closest('.mb-3')?.querySelector('.form-label');
        if (label && !label.querySelector('.save-error-indicator')) {
            const indicator = document.createElement('span');
            indicator.className = 'save-error-indicator text-danger fw-bold me-1';
            indicator.textContent = '!';
            label.prepend(indicator);
        }

        // insert feedback div
        if (!input.parentElement.querySelector('.invalid-feedback[data-save-error]')) {
            const feedback = document.createElement('div');
            feedback.className = 'invalid-feedback';
            feedback.dataset.saveError = '1';
            feedback.textContent = msg;
            input.parentElement.appendChild(feedback);
        }

        // clear on next input
        input.addEventListener('input', function clearErr() {
            input.classList.remove('is-invalid');
            input.parentElement.querySelectorAll('.invalid-feedback[data-save-error]').forEach(el => el.remove());
            const ind = label?.querySelector('.save-error-indicator');
            if (ind) {ind.remove();}
            input.removeEventListener('input', clearErr);
        }, { once: true });
    }
}

function _toast(message, type = 'primary') {
    // reuse legacy showNotification if available, otherwise simple fallback
    if (typeof window.showNotification === 'function') {
        window.showNotification(message, type);
        return;
    }
    // minimal fallback
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        container.style.zIndex = '9999';
        document.body.appendChild(container);
    }
    const id = `toast-${Date.now()}`;
    container.insertAdjacentHTML('beforeend', `
        <div id="${id}" class="toast align-items-center text-bg-${type} border-0" role="alert">
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `);
    const el = document.getElementById(id);
    const toast = new bootstrap.Toast(el, { autohide: true, delay: 3000 });
    toast.show();
    el.addEventListener('hidden.bs.toast', () => el.remove());
}
