/**
 * Form Handling Module
 * Parallels forms.py - form serialization and validation
 */

/**
 * Serialize form to JSON object with nested structure
 */
export function serializeForm(form) {
    const formData = new FormData(form);
    const data = {};

    for (const [key, value] of formData.entries()) {
        // Handle nested keys (e.g., "channels.activity")
        if (key.includes(".")) {
            const parts = key.split(".");
            let current = data;
            for (let i = 0; i < parts.length - 1; i++) {
                if (!current[parts[i]]) {
                    current[parts[i]] = {};
                }
                current = current[parts[i]];
            }
            const lastKey = parts[parts.length - 1];
            current[lastKey] = parseValue(value);
        } else {
            data[key] = parseValue(value);
        }
    }

    // Handle unchecked checkboxes
    form.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
        if (!checkbox.checked) {
            const key = checkbox.name;
            if (key.includes(".")) {
                const parts = key.split(".");
                let current = data;
                for (let i = 0; i < parts.length - 1; i++) {
                    if (!current[parts[i]]) {
                        current[parts[i]] = {};
                    }
                    current = current[parts[i]];
                }
                current[parts[parts.length - 1]] = false;
            } else {
                data[key] = false;
            }
        }
    });

    return data;
}

/**
 * Parse form value to appropriate type
 */
function parseValue(value) {
    // Try to parse as number
    if (!isNaN(value) && value !== "") {
        const num = Number(value);
        if (Number.isSafeInteger(num)) {
            return num;
        }
        // Large integer, keep as string
        if (value.match(/^-?\d+$/)) {
            return value;
        }
        return num;
    }

    // Handle booleans
    if (value === "true") return true;
    if (value === "false") return false;

    // Handle comma-separated lists
    if (typeof value === "string" && value.includes(",")) {
        return value
            .split(",")
            .map((v) => v.trim())
            .filter((v) => v)
            .map((v) => parseValue(v));
    }

    return value;
}

/**
 * Populate form field with value
 */
export function populateField(name, value) {
    const field = document.querySelector(`[name="${name}"]`);
    if (!field) {
        console.warn(`Field not found: ${name}`);
        return;
    }

    if (field.type === "checkbox") {
        field.checked = value;
    } else {
        field.value = value;
    }
}
