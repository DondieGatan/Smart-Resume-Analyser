/* Resume Builder, part 1 of 3: the draft (state, saved in this browser), the step forms, the live preview, the
   progress bar, autosave, Clean Writing. Loaded first; publishes a small API as window.Builder for pdf.js and
   assistant.js. Config comes from the JSON block the page renders (#builder-config), never from inline code. */
(function () {
var CONFIG = JSON.parse(document.getElementById('builder-config').textContent);
var TEMPLATE_ID = CONFIG.templateId;
var SECTIONS = CONFIG.sections;
var DRAFT_KEY = 'builderDraft_' + TEMPLATE_ID;

// draftData.sections[sectionIndex] is either a string (type: 'text')
// or an array of field-objects (type: 'repeatable'). Indexes are 1-based positions (they key the saved drafts).
var draftData = { sections: {} };
var autosaveTimer = null;

// ---------- Escaping ----------
function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ---------- Repeatable-entry rendering ----------
function makeEmptyEntry(fields) {
    var entry = {};
    fields.forEach(function(f) { entry[f.key] = ''; });
    return entry;
}

function onFieldInput(e) {
    var el = e.target;
    var sectionIndex = el.dataset.section;
    var entryIdx = parseInt(el.dataset.entry, 10);
    var field = el.dataset.field;
    draftData.sections[sectionIndex][entryIdx][field] = el.value;
    scheduleAutosave();
    generatePreview();
    updateProgress();
}

function renderEntries(sectionIndex) {
    var section = SECTIONS[sectionIndex - 1];
    var container = document.getElementById('entries-' + sectionIndex);
    var entries = draftData.sections[sectionIndex] || [];
    if (entries.length === 0) {
        entries = [makeEmptyEntry(section.fields)];
        draftData.sections[sectionIndex] = entries;
    }
    container.innerHTML = '';
    entries.forEach(function(entry, entryIdx) {
        var card = document.createElement('div');
        card.className = 'entry-card';

        var header = document.createElement('div');
        header.className = 'entry-header';
        var label = document.createElement('span');
        label.textContent = section.name + ' #' + (entryIdx + 1);
        header.appendChild(label);
        if (entries.length > 1) {
            var removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'remove-entry-btn';
            removeBtn.textContent = 'Remove';
            removeBtn.addEventListener('click', function() { removeEntry(sectionIndex, entryIdx); });
            header.appendChild(removeBtn);
        }
        card.appendChild(header);

        section.fields.forEach(function(field) {
            var group = document.createElement('div');
            group.className = 'form-group';
            var lbl = document.createElement('label');
            lbl.textContent = field.label;
            group.appendChild(lbl);

            var input;
            if (field.type === 'textarea') {
                input = document.createElement('textarea');
                input.rows = 4;
                input.className = 'builder-textarea';
            } else {
                input = document.createElement('input');
                input.type = 'text';
            }
            input.placeholder = field.placeholder || '';
            input.value = entry[field.key] || '';
            input.dataset.section = sectionIndex;
            input.dataset.entry = entryIdx;
            input.dataset.field = field.key;
            input.addEventListener('input', onFieldInput);
            group.appendChild(input);
            card.appendChild(group);
        });

        container.appendChild(card);
    });
}

function addEntry(sectionIndex) {
    var section = SECTIONS[sectionIndex - 1];
    draftData.sections[sectionIndex].push(makeEmptyEntry(section.fields));
    renderEntries(sectionIndex);
    scheduleAutosave();
    generatePreview();
    updateProgress();
}

function removeEntry(sectionIndex, entryIdx) {
    draftData.sections[sectionIndex].splice(entryIdx, 1);
    renderEntries(sectionIndex);
    scheduleAutosave();
    generatePreview();
    updateProgress();
}

// ---------- Unified section -> display text ----------
function getSectionDisplayText(sectionIndex) {
    var section = SECTIONS[sectionIndex - 1];
    if (section.type === 'repeatable') {
        var entries = draftData.sections[sectionIndex] || [];
        var blocks = [];
        entries.forEach(function(entry) {
            var headerParts = [];
            var bodyLines = [];
            section.fields.forEach(function(field) {
                var val = (entry[field.key] || '').trim();
                if (!val) return;
                if (field.type === 'textarea') {
                    bodyLines.push(val);
                } else {
                    headerParts.push(val);
                }
            });
            if (!headerParts.length && !bodyLines.length) return;
            var block = '';
            if (headerParts.length) {
                block = headerParts[0];
                if (headerParts.length > 1) {
                    block += ' — ' + headerParts.slice(1).join(' | ');
                }
            }
            if (bodyLines.length) {
                block += (block ? '\n' : '') + bodyLines.join('\n');
            }
            if (block.trim()) blocks.push(block.trim());
        });
        return blocks.join('\n\n');
    }
    var ta = document.getElementById('section-' + sectionIndex);
    return ta ? ta.value.trim() : '';
}

function hasAnyContent() {
    for (var i = 1; i <= SECTIONS.length; i++) {
        if (getSectionDisplayText(i)) return true;
    }
    return false;
}

function getResumeFileBaseName() {
    var contactText = getSectionDisplayText(1);
    var nameField = contactText ? contactText.split('\n')[0].trim() : 'Resume';
    var fileName = (nameField || 'Resume').replace(/[^a-zA-Z0-9\s]/g, '').trim().replace(/\s+/g, '_') || 'Resume';
    if (fileName.length > 40) fileName = fileName.substring(0, 40);
    return fileName;
}

// ---------- Progress tracker ----------
function isSectionComplete(sectionIndex) {
    var section = SECTIONS[sectionIndex - 1];
    if (section.type === 'repeatable') {
        var entries = draftData.sections[sectionIndex] || [];
        return entries.some(function(entry) {
            return Object.keys(entry).some(function(k) { return (entry[k] || '').trim(); });
        });
    }
    var ta = document.getElementById('section-' + sectionIndex);
    return !!(ta && ta.value.trim());
}

function updateProgress() {
    var total = SECTIONS.length;
    var completed = 0;
    for (var i = 1; i <= total; i++) {
        if (isSectionComplete(i)) completed++;
    }
    var pct = total ? Math.round((completed / total) * 100) : 0;
    document.getElementById('progress-text').textContent = completed + ' of ' + total + ' sections completed';
    document.getElementById('progress-fill').style.width = pct + '%';
}

// ---------- Preview / Copy ----------
function generatePreview() {
    var preview = document.getElementById('resume-preview');
    var html = '';
    var hasContent = false;

    for (var i = 1; i <= SECTIONS.length; i++) {
        var text = getSectionDisplayText(i);
        if (text) {
            hasContent = true;
            html += '<div class="preview-section">';
            html += '<h4>' + escapeHtml(SECTIONS[i - 1].name) + '</h4>';
            html += '<p>' + escapeHtml(text).replace(/\n/g, '<br>') + '</p>';
            html += '</div>';
        }
    }

    if (!hasContent) {
        html = '<p style="color:var(--gray-400);text-align:center;">Fill in the sections above to see your preview.</p>';
    }
    preview.innerHTML = html;
}

function copyResume() {
    var text = '';
    for (var i = 1; i <= SECTIONS.length; i++) {
        var content = getSectionDisplayText(i);
        if (content) {
            text += SECTIONS[i - 1].name.toUpperCase() + '\n';
            text += content + '\n\n';
        }
    }

    if (!text) {
        alert('Please fill in at least one section first.');
        return;
    }

    navigator.clipboard.writeText(text).then(function() {
        var btn = document.getElementById('copy-btn');
        btn.textContent = 'Copied!';
        setTimeout(function() { btn.textContent = 'Copy to Clipboard'; }, 2000);
    });
}

// ---------- Autosave / restore / clear ----------
function timeAgo(ts) {
    var seconds = Math.round((Date.now() - ts) / 1000);
    if (seconds < 10) return 'just now';
    if (seconds < 60) return seconds + 's ago';
    var minutes = Math.round(seconds / 60);
    if (minutes < 60) return minutes + 'm ago';
    var hours = Math.round(minutes / 60);
    return hours + 'h ago';
}

function updateDraftStatus(savedAt) {
    var el = document.getElementById('draft-status');
    if (!el) return;
    el.textContent = savedAt ? ('Last saved: ' + timeAgo(savedAt)) : '';
}

/* Saved drafts are keyed by section id ("summary"), not by position, so adding or reordering sections can never
   move someone's text into the wrong box. In memory the draft is still indexed by position (the form's element
   ids use it); these two functions convert at the storage boundary. Version 1 drafts, saved before this and keyed
   by position, are read and rewritten in the new form the next time the draft is saved. */
function draftForStorage() {
    var out = {};
    SECTIONS.forEach(function (section, i) { out[section.id] = draftData.sections[i + 1]; });
    return out;
}

function draftFromStorage(stored) {
    if (!stored || typeof stored !== 'object' || !stored.sections) return stored;
    var byIndex = {};
    SECTIONS.forEach(function (section, i) {
        var value = stored.version === 2 ? stored.sections[section.id] : stored.sections[i + 1];
        if (value !== undefined) byIndex[i + 1] = value;
    });
    stored.sections = byIndex;
    return stored;
}

function saveDraft() {
    try {
        localStorage.setItem(DRAFT_KEY, JSON.stringify({ version: 2, sections: draftForStorage(), savedAt: Date.now() }));
        updateDraftStatus(Date.now());
    } catch (e) {
        // localStorage unavailable (private mode, quota, etc.) — nothing to autosave against
    }
}

function scheduleAutosave() {
    if (autosaveTimer) clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(saveDraft, 500);
}

function loadDraft() {
    var raw;
    try {
        raw = localStorage.getItem(DRAFT_KEY);
    } catch (e) {
        return null;
    }
    if (!raw) return null;
    try {
        return draftFromStorage(JSON.parse(raw));
    } catch (e) {
        return null;
    }
}

function clearDraft() {
    showConfirmModal(
        'Clear everything you\'ve entered for this template? This cannot be undone.',
        { title: 'Clear this draft?', confirmLabel: 'Clear Draft' }
    ).then(function(ok) {
        if (!ok) return;
        try { localStorage.removeItem(DRAFT_KEY); } catch (e) { /* nothing to clear */ }

        draftData = { sections: {} };
        SECTIONS.forEach(function(section, i) {
            var idx = i + 1;
            if (section.type === 'repeatable') {
                draftData.sections[idx] = [];
                renderEntries(idx);
            } else {
                draftData.sections[idx] = '';
                var ta = document.getElementById('section-' + idx);
                if (ta) ta.value = '';
            }
        });
        updateDraftStatus(null);
        generatePreview();
        updateProgress();
    });
}

// ---------- Grammar & Spell Check ----------
function cleanWriting(text) {
    var cleaned = text;

    // Protect emails, URLs, and special tokens from being mangled
    var preserved = [];
    cleaned = cleaned.replace(/[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}/g, function(match) {
        preserved.push(match);
        return '%%PRESERVE' + (preserved.length - 1) + '%%';
    });
    cleaned = cleaned.replace(/https?:\/\/[^\s]+/g, function(match) {
        preserved.push(match);
        return '%%PRESERVE' + (preserved.length - 1) + '%%';
    });
    cleaned = cleaned.replace(/www\.[^\s]+/g, function(match) {
        preserved.push(match);
        return '%%PRESERVE' + (preserved.length - 1) + '%%';
    });

    // Fix double spaces
    cleaned = cleaned.replace(/  +/g, ' ');

    // Capitalize first letter of each sentence
    cleaned = cleaned.replace(/(^|[.!?]\s+)([a-z])/gm, function(match, prefix, letter) {
        return prefix + letter.toUpperCase();
    });

    // Capitalize first letter of each line
    cleaned = cleaned.replace(/^([a-z])/gm, function(match, letter) {
        return letter.toUpperCase();
    });

    // Fix common typos / misspellings
    var typos = {
        'teh': 'the', 'adn': 'and', 'taht': 'that', 'wiht': 'with',
        'hte': 'the', 'recieve': 'receive', 'acheive': 'achieve',
        'occured': 'occurred', 'seperate': 'separate', 'definately': 'definitely',
        'accomodate': 'accommodate', 'occassion': 'occasion', 'neccessary': 'necessary',
        'succesful': 'successful', 'proffesional': 'professional', 'managment': 'management',
        'responsibilty': 'responsibility', 'developement': 'development',
        'enviroment': 'environment', 'comunication': 'communication',
        'independant': 'independent', 'expereince': 'experience', 'experiance': 'experience',
        'knowlege': 'knowledge', 'languange': 'language', 'maintainance': 'maintenance',
        'preformance': 'performance', 'recomendation': 'recommendation',
        'strenght': 'strength', 'strenghts': 'strengths', 'technolgy': 'technology',
        'undrestand': 'understand', 'writting': 'writing', 'wich': 'which',
        'becuase': 'because', 'beleive': 'believe', 'calender': 'calendar',
        'collegue': 'colleague', 'comittee': 'committee', 'completly': 'completely',
        'consciencious': 'conscientious', 'consistant': 'consistent',
        'curriculm': 'curriculum', 'efficent': 'efficient', 'excellant': 'excellent',
        'excercise': 'exercise', 'foriegn': 'foreign', 'goverment': 'government',
        'immediatly': 'immediately', 'liason': 'liaison', 'occurance': 'occurrence',
        'persistant': 'persistent', 'posession': 'possession', 'priviledge': 'privilege',
        'pronounciation': 'pronunciation', 'publically': 'publicly',
        'referencs': 'references', 'relevent': 'relevant', 'responsable': 'responsible',
        'succesfully': 'successfully', 'transfered': 'transferred',
        'manageable': 'manageable', 'judgement': 'judgment'
    };

    Object.keys(typos).forEach(function(wrong) {
        var regex = new RegExp('\\b' + wrong + '\\b', 'gi');
        cleaned = cleaned.replace(regex, function(match) {
            var fix = typos[wrong];
            if (match[0] === match[0].toUpperCase()) {
                return fix.charAt(0).toUpperCase() + fix.slice(1);
            }
            return fix;
        });
    });

    // Fix missing space after punctuation
    cleaned = cleaned.replace(/([.!?,;:])([A-Za-z])/g, '$1 $2');

    // Fix repeated punctuation (.. or ,, but not ... ellipsis)
    cleaned = cleaned.replace(/([.!?,;:])\1{1}(?!\1)/g, '$1');

    // Remove trailing spaces on each line
    cleaned = cleaned.replace(/[ \t]+$/gm, '');

    // Fix common grammar: "i" -> "I" standalone
    cleaned = cleaned.replace(/\bi\b(?=[^.])/g, 'I');
    cleaned = cleaned.replace(/(^|\s)i(\s|[',.])/gm, '$1I$2');

    // Restore preserved emails and URLs
    for (var p = 0; p < preserved.length; p++) {
        cleaned = cleaned.replace('%%PRESERVE' + p + '%%', preserved[p]);
    }

    return cleaned;
}

function cleanAllTextareas() {
    var totalFixes = 0;
    var fields = [];

    SECTIONS.forEach(function(section, i) {
        var idx = i + 1;
        if (section.type === 'repeatable') {
            var container = document.getElementById('entries-' + idx);
            if (container) {
                fields = fields.concat(Array.prototype.slice.call(container.querySelectorAll('input, textarea')));
            }
        } else {
            var ta = document.getElementById('section-' + idx);
            if (ta) fields.push(ta);
        }
    });

    fields.forEach(function(el) {
        var original = el.value;
        if (!original.trim()) return;

        var cleaned = cleanWriting(original);
        if (cleaned !== original) {
            var fixes = 0;
            for (var c = 0; c < Math.max(original.length, cleaned.length); c++) {
                if (original[c] !== cleaned[c]) fixes++;
            }
            totalFixes += Math.max(1, Math.floor(fixes / 3));
            el.value = cleaned;
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }
    });

    generatePreview();

    var btn = document.getElementById('clean-btn');
    if (totalFixes > 0) {
        btn.textContent = 'Cleaned ' + totalFixes + ' issue' + (totalFixes > 1 ? 's' : '') + '!';
        btn.style.background = 'var(--success)';
    } else {
        btn.textContent = 'Writing looks clean!';
        btn.style.background = 'var(--success)';
    }
    setTimeout(function() {
        btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" style="vertical-align:-2px;margin-right:6px;"><path d="M2 1a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1H2zm5.854 8.803l-2.5 2.5a.5.5 0 0 1-.708 0l-1.5-1.5a.5.5 0 1 1 .708-.708L5 11.293l2.146-2.147a.5.5 0 0 1 .708.657z"/></svg> Clean Writing';
        btn.style.background = '';
    }, 2500);
}

// ---------- Init: restore any saved draft, wire up text-section listeners ----------
(function init() {
    var restored = loadDraft();

    SECTIONS.forEach(function(section, i) {
        var idx = i + 1;
        if (section.type === 'repeatable') {
            var savedEntries = restored && restored.sections && restored.sections[idx];
            draftData.sections[idx] = (savedEntries && savedEntries.length) ? savedEntries : [];
            renderEntries(idx);
        } else {
            var savedText = (restored && restored.sections && typeof restored.sections[idx] === 'string')
                ? restored.sections[idx] : '';
            draftData.sections[idx] = savedText;
            var ta = document.getElementById('section-' + idx);
            if (ta) {
                ta.value = savedText;
                ta.addEventListener('input', function() {
                    draftData.sections[idx] = ta.value;
                    scheduleAutosave();
                    generatePreview();
                    updateProgress();
                });
            }
        }
    });

    if (restored && restored.savedAt) {
        updateDraftStatus(restored.savedAt);
    }


    generatePreview();
    updateProgress();
})();

// ---------- Wiring (buttons used to carry inline onclick attributes) ----------
function onClick(id, fn) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('click', fn);
}
onClick('clean-btn', cleanAllTextareas);
onClick('preview-btn', generatePreview);
onClick('clear-draft-btn', clearDraft);
onClick('copy-btn', copyResume);
Array.prototype.forEach.call(document.querySelectorAll('.add-entry-btn'), function (btn) {
    btn.addEventListener('click', function () { addEntry(parseInt(btn.dataset.section, 10)); });
});

// ---------- What the other builder scripts may use ----------
function indexOfSection(id) {
    for (var i = 0; i < SECTIONS.length; i++) if (SECTIONS[i].id === id) return i + 1;
    return 0;
}

/* The draft as {section id: plain text}, the shape the AI assistant is sent. */
function draftByText() {
    var out = {};
    SECTIONS.forEach(function (s, i) { out[s.id] = getSectionDisplayText(i + 1); });
    return out;
}

/* Puts text into a single-text-block section as if the user had typed it. Returns the textarea, or null. */
function setSectionText(index, text) {
    var section = SECTIONS[index - 1];
    var ta = document.getElementById('section-' + index);
    if (!section || section.type === 'repeatable' || !ta) return null;
    ta.value = text;
    // the textarea's own input listener (see init) syncs the draft, autosave, preview and progress
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    return ta;
}

window.Builder = {
    config: CONFIG,
    sections: SECTIONS,
    sectionText: getSectionDisplayText,
    hasContent: hasAnyContent,
    fileBaseName: getResumeFileBaseName,
    refreshPreview: generatePreview,
    entries: function (index) { return draftData.sections[index] || []; },
    indexOfSection: indexOfSection,
    draftByText: draftByText,
    setSectionText: setSectionText
};
})();
