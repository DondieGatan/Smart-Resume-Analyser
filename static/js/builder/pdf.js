/* Resume Builder, part 2 of 3: builds the PDF (a real text layer, which employer ATS systems can read) for
   Export, and for "Analyse This Resume". Needs core.js and the jsPDF library loaded before it. */
(function () {
var B = window.Builder;
var SECTIONS = B.sections;
var getSectionDisplayText = B.sectionText;
var hasAnyContent = B.hasContent;
var getResumeFileBaseName = B.fileBaseName;
var generatePreview = B.refreshPreview;

// ---------- Native-text PDF builder (used by Export and Analyse) ----------
// Draws real, embedded PDF text via jsPDF directly, rather than rasterizing
// an HTML element through html2canvas the way the previous version did.
// That image-based approach meant the file had no actual text layer at all
// — this app's own analyser could still read it via an OCR fallback, but a
// real employer's ATS almost certainly can't, since most don't run OCR on
// uploaded resumes. Colors and layout are matched to a clean, single-column
// reference resume: a navy name/section-header accent, black body text, and
// gray italic meta text. Helvetica (jsPDF's built-in, closest to Arial) is
// one of the most broadly ATS-recommended fonts.
var PDF_ACCENT = [31, 56, 99];   // #1F3863 navy — name, section headers, dividers
var PDF_TEXT = [0, 0, 0];        // pure black — body text
var PDF_META = [84, 84, 84];     // #545454 gray — italic company/institution/dates

var PDF_MARGIN_L = 46, PDF_MARGIN_R = 46, PDF_MARGIN_TOP = 44, PDF_MARGIN_BOTTOM = 44;

function buildResumePdfDoc() {
    var doc = new window.jspdf.jsPDF({ unit: 'pt', format: 'letter' });
    var pageW = doc.internal.pageSize.getWidth();
    var pageH = doc.internal.pageSize.getHeight();
    var contentW = pageW - PDF_MARGIN_L - PDF_MARGIN_R;
    var y = PDF_MARGIN_TOP;

    function ensureSpace(h) {
        if (y + h > pageH - PDF_MARGIN_BOTTOM) {
            doc.addPage();
            y = PDF_MARGIN_TOP;
        }
    }

    function setColor(rgb) { doc.setTextColor(rgb[0], rgb[1], rgb[2]); }

    // Draws already-wrapped lines one at a time (rather than in one text()
    // call) so a page break can land mid-paragraph. Justifies every line
    // except the last, matching normal typographic convention — a short
    // final line shouldn't get stretched to fill the column.
    function drawWrapped(lines, x, width, lineHeight, justify) {
        lines.forEach(function(line, i) {
            ensureSpace(lineHeight);
            if (justify && i < lines.length - 1) {
                doc.text(line, x, y, { align: 'justify', maxWidth: width });
            } else {
                doc.text(line, x, y);
            }
            y += lineHeight;
        });
    }

    function drawDivider() {
        doc.setDrawColor(PDF_ACCENT[0], PDF_ACCENT[1], PDF_ACCENT[2]);
        doc.setLineWidth(1);
        doc.line(PDF_MARGIN_L, y, pageW - PDF_MARGIN_R, y);
        y += 10;
    }

    function drawBullets(lines) {
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(10.5);
        setColor(PDF_TEXT);
        lines.forEach(function(text) {
            var wrapped = doc.splitTextToSize('•  ' + text, contentW - 12);
            drawWrapped(wrapped, PDF_MARGIN_L + 12, contentW - 12, 14, true);
        });
        if (lines.length) y += 4;
    }

    // ---- Header: first section is Contact Information — its first line
    // becomes the name, the rest becomes one contact line ----
    var startIndex = 1;
    var contactTa = document.getElementById('section-1');
    if (SECTIONS[0] && SECTIONS[0].type !== 'repeatable' && contactTa && contactTa.value.trim()) {
        var contactLines = contactTa.value.split('\n').map(function(l) { return l.trim(); }).filter(Boolean);

        doc.setFont('helvetica', 'bold');
        doc.setFontSize(22);
        setColor(PDF_ACCENT);
        doc.text(contactLines[0], PDF_MARGIN_L, y);
        y += 24;

        var rest = contactLines.slice(1);
        if (rest.length) {
            doc.setFont('helvetica', 'normal');
            doc.setFontSize(10);
            setColor(PDF_TEXT);
            var contactWrapped = doc.splitTextToSize(rest.join('   |   '), contentW);
            drawWrapped(contactWrapped, PDF_MARGIN_L, contentW, 13, false);
            y += 4;
        }
        drawDivider();
        y += 4;
        startIndex = 2;
    }

    for (var i = startIndex; i <= SECTIONS.length; i++) {
        var section = SECTIONS[i - 1];
        if (!getSectionDisplayText(i)) continue;

        ensureSpace(30);
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(12);
        setColor(PDF_ACCENT);
        // "(Optional)" is builder-UI guidance, not resume content — strip it.
        doc.text(section.name.replace(/\s*\(Optional\)\s*$/i, '').toUpperCase(), PDF_MARGIN_L, y);
        y += 6;
        drawDivider();
        y += 6;

        if (section.type === 'repeatable') {
            var entries = B.entries(i);
            entries.forEach(function(entry) {
                var headerParts = [];
                var descLines = [];
                section.fields.forEach(function(field) {
                    var val = (entry[field.key] || '').trim();
                    if (!val) return;
                    if (field.type === 'textarea') {
                        descLines = descLines.concat(val.split('\n').map(function(l) { return l.replace(/^[-•]\s*/, '').trim(); }).filter(Boolean));
                    } else {
                        headerParts.push(val);
                    }
                });
                if (!headerParts.length && !descLines.length) return;

                if (headerParts.length) {
                    ensureSpace(15);
                    doc.setFont('helvetica', 'bold');
                    doc.setFontSize(11);
                    setColor(PDF_TEXT);
                    doc.text(headerParts[0], PDF_MARGIN_L, y);
                    var titleW = doc.getTextWidth(headerParts[0]);

                    if (headerParts.length > 1) {
                        doc.setFont('helvetica', 'italic');
                        doc.setFontSize(10);
                        setColor(PDF_META);
                        doc.text('   —   ' + headerParts.slice(1).join('  |  '), PDF_MARGIN_L + titleW, y);
                    }
                    y += 15;
                }

                drawBullets(descLines);
            });
        } else {
            var rawLines = (document.getElementById('section-' + i) || { value: '' }).value.split('\n');
            var bulletBuffer = [];

            rawLines.forEach(function(line) {
                var trimmed = line.trim();
                if (!trimmed) {
                    drawBullets(bulletBuffer);
                    bulletBuffer = [];
                    return;
                }

                var bulletMatch = trimmed.match(/^[-•]\s*(.+)/);
                if (bulletMatch) {
                    bulletBuffer.push(bulletMatch[1]);
                    return;
                }
                drawBullets(bulletBuffer);
                bulletBuffer = [];

                // Bold a leading "Label:" (used by Skills, e.g. "Technical Skills: Python, SQL").
                var labelMatch = trimmed.match(/^([A-Za-z][A-Za-z0-9 &/]{1,40}):\s*(.+)/);
                ensureSpace(14);
                if (labelMatch) {
                    doc.setFont('helvetica', 'bold');
                    doc.setFontSize(10.5);
                    setColor(PDF_TEXT);
                    var label = labelMatch[1] + ': ';
                    doc.text(label, PDF_MARGIN_L, y);
                    var labelW = doc.getTextWidth(label);
                    doc.setFont('helvetica', 'normal');
                    var valueWrapped = doc.splitTextToSize(labelMatch[2], contentW - labelW);
                    doc.text(valueWrapped[0] || '', PDF_MARGIN_L + labelW, y);
                    y += 14;
                    if (valueWrapped.length > 1) {
                        drawWrapped(valueWrapped.slice(1), PDF_MARGIN_L, contentW, 14, false);
                    }
                } else {
                    doc.setFont('helvetica', 'normal');
                    doc.setFontSize(10.5);
                    setColor(PDF_TEXT);
                    var wrapped = doc.splitTextToSize(trimmed, contentW);
                    drawWrapped(wrapped, PDF_MARGIN_L, contentW, 14, true);
                }
            });
            drawBullets(bulletBuffer);
        }

        y += 10;
    }

    return doc;
}

function exportPDF() {
    generatePreview();

    if (!hasAnyContent()) {
        alert('Please fill in at least one section first.');
        return;
    }

    var fileName = getResumeFileBaseName();
    var btn = document.getElementById('export-btn');
    var originalHTML = btn.innerHTML;
    btn.innerHTML = '<span style="display:inline-block;width:14px;height:14px;border:2px solid #fff;border-top:2px solid transparent;border-radius:50%;animation:spin 0.8s linear infinite;vertical-align:-2px;margin-right:6px;"></span> Generating PDF...';
    btn.disabled = true;

    setTimeout(function() {
        try {
            var doc = buildResumePdfDoc();
            doc.save(fileName + '_Resume.pdf');
            btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" style="vertical-align:-2px;margin-right:6px;"><path d="M.5 9.9a.5.5 0 0 1 .5.5v2.5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-2.5a.5.5 0 0 1 1 0v2.5a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2v-2.5a.5.5 0 0 1 .5-.5z"/><path d="M7.646 11.854a.5.5 0 0 0 .708 0l3-3a.5.5 0 0 0-.708-.708L8.5 10.293V1.5a.5.5 0 0 0-1 0v8.793L5.354 8.146a.5.5 0 1 0-.708.708l3 3z"/></svg> Exported!';
            setTimeout(function() { btn.innerHTML = originalHTML; btn.disabled = false; }, 2000);
        } catch (err) {
            console.error('PDF generation failed:', err);
            btn.innerHTML = 'Export Failed - Try Again';
            btn.disabled = false;
            setTimeout(function() { btn.innerHTML = originalHTML; btn.disabled = false; }, 3000);
        }
    }, 50);
}

function analyzeNow() {
    generatePreview();

    if (!hasAnyContent()) {
        alert('Please fill in at least one section first.');
        return;
    }

    var fileName = getResumeFileBaseName();
    var btn = document.getElementById('analyze-btn');
    var originalHTML = btn.innerHTML;
    btn.innerHTML = '<span style="display:inline-block;width:14px;height:14px;border:2px solid #fff;border-top:2px solid transparent;border-radius:50%;animation:spin 0.8s linear infinite;vertical-align:-2px;margin-right:6px;"></span> Preparing...';
    btn.disabled = true;

    setTimeout(function() {
        try {
            var doc = buildResumePdfDoc();
            var blob = doc.output('blob');
            var file = new File([blob], fileName + '_Resume.pdf', { type: 'application/pdf' });
            var dt = new DataTransfer();
            dt.items.add(file);
            document.getElementById('analyze-file-input').files = dt.files;
            document.getElementById('analyze-form').submit();
        } catch (err) {
            console.error('PDF generation for analysis failed:', err);
            btn.innerHTML = 'Failed - Try Again';
            btn.disabled = false;
            setTimeout(function() { btn.innerHTML = originalHTML; btn.disabled = false; }, 3000);
        }
    }, 50);
}

function onClick(id, fn) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('click', fn);
}
onClick('export-btn', exportPDF);
onClick('analyze-btn', analyzeNow);
})();
