/**
 * SmartMailer Ultimate — Professional Dashboard Application v2
 * New: Sent Mail Viewer, Follow-Up Engine tab, Agent Self-Improvement,
 * Duplicate Prevention, Brevo spam info, Sector Tags
 */

const API = '';
let leadsData = [];
let sortState = { key: '', dir: 'asc' };
let selectedLeads = new Set();
let autoRefreshInterval = null;
let logRefreshInterval = null;
let currentLeadFilter = 'all';

const AGENT_DESC = {
    'Orchestrator': 'Tüm agent ekosistemini yöneten başkomutan. Otomasyon pipeline\'ını koordine eder, agent\'lar arası iletişimi sağlar, toplantıları yönetir. Her cycle sonunda performans analizi yapar ve stratejik kararlar alır. Sistem genelindeki optimizasyonu sağlar.',
    'AI Copywriter': 'Claude AI ile her lead için kişiselleştirilmiş, profesyonel email yazar. Şirket adı, sektörü ve detaylarına göre özgün içerik oluşturur. 3 farklı konu başlığı (A/B/C) üretir. ReconAgent istihbaratını kullanarak her emaili hedefin psikolojik profiline göre yazar.',
    'AI Quality Control': 'Yazılan emailleri 15+ kriterde puanlar (konu uzunluğu, spam kelimeleri, kişiselleştirme, CTA, dil hatası, vb). ≥90 puan geçer, altında otomatik revize edilir. Her revizeden sonra puanı neden düştüğünü öğrenir ve gelecekte aynı hatayı yapmaktan kaçınır.',
    'Compliance (AVG)': 'GDPR/AVG uyumluluğunu kontrol eder. Unsubscribe listesi, bounce listesi ve opt-out kayıtlarını yönetir. Her emailde yasal bilgi footeri ekler.',
    'Lead Scorer': 'Claude AI ile lead kalitesini puanlar: şirket büyüklüğü, sektör uyumu, web varlığı, potansiyel filo büyüklüğü gibi kriterlere göre 0-100 puan verir. Hangi tür leadlerin yanıt verdiğini takip edip puanlama modelini geliştirir.',
    'Watchdog': 'Tüm sistemin sağlığını izler: API bağlantıları, veritabanı, email gönderim durumu, agent sağlıkları. Sorun tespit ederse uyarı verir.',
    'A/B Test Engine': '12 email gönderdikten sonra A/B/C konu başlıklarından hangisinin daha çok açıldığını analiz eder. Kazananı otomatik seçer. Zamanla en etkili konu formatını keşfeder.',
    'Follow-Up Engine': '3 aşamalı gelişmiş follow-up sistemi: Gün 3 — Social Proof + Curiosity Gap, Gün 7 — ROI Case Study + Value-Add, Gün 14 — FOMO + Scarcity + Loss Aversion ile kapanış. Önceki maillere atıfta bulunarak yazılır. Her aşamada farklı psikolojik teknikler kullanılır.',
    'Response Tracker': 'Gelen yanıtları Claude AI ile sınıflar: İlgili, İlgisiz, Soru, Ofis dışı. İlgili yanıtlar hot lead olarak işaretlenir. Sınıflandırma doğruluğunu sürekli iyileştirir.',
    'Lead Finder': '10+ kaynaktan lead keşfi: DeTelefoongids, Opendi, Telefoonboek.nl, OpenStreetMap, Bing, DuckDuckGo, Startpage, AI bilgi bankası, website crawl, email tahmini. Paralel 5 şehir taraması. Hangi kaynakların daha kaliteli lead verdiğini öğrenir.',
    'Recon Agent': 'Mail göndermeden ÖNCE hedef şirket hakkında derinlemesine araştırma yapan OSINT ajanı. 3 katmanlı analiz: 1) Website scraping (about, team, services), 2) Email/domain intelligence (kişi adı, rol tespiti), 3) Claude AI ile psikolojik profil — Cialdini\'nin 6 ikna prensibi, Kahneman System 1/2, Maslow ihtiyaçlar hiyerarşisi, nudging teknikleri. Her lead için benzersiz ikna stratejisi üretir.',
};

// ═══ TAB NAVIGATION ═══
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

function switchTab(tab) {
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    const navBtn = document.querySelector(`[data-tab="${tab}"]`);
    if (navBtn) navBtn.classList.add('active');
    const tabEl = document.getElementById(`tab-${tab}`);
    if (tabEl) tabEl.classList.add('active');
    stopLogPolling();

    switch (tab) {
        case 'dashboard': refreshAll(); break;
        case 'leads': loadLeads(); break;
        case 'sentmails': loadSentMails(); break;
        case 'followup': loadFollowUpEngine(); break;
        case 'campaign': loadCampaignStatus(); break;
        case 'agents': loadAgentStatus(); break;
        case 'automation': loadAutomationStatus(); loadLogs('automation-log'); startLogPolling(); break;
        case 'responses': loadResponses(); break;
        case 'settings': loadSettings(); loadLogs('logs-container'); break;
    }
}

// ═══ API HELPER ═══
async function api(path, method = 'GET', body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    try {
        const res = await fetch(`${API}${path}`, opts);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (err) { console.error(`API [${path}]:`, err); return null; }
}

// ═══ TOAST ═══
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icons = { success: '✅', error: '❌', info: '⚡' };
    toast.innerHTML = `<span>${icons[type] || ''}</span><span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 4000);
}

// ═══ MODAL ═══
function openModal(title, content) {
    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-body').innerHTML = content;
    document.getElementById('modal-overlay').classList.add('visible');
    document.body.style.overflow = 'hidden';
}
function closeModal() {
    document.getElementById('modal-overlay').classList.remove('visible');
    document.body.style.overflow = '';
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ═══════════════════════════════════════════════════════════
// DASHBOARD
// ═══════════════════════════════════════════════════════════
async function refreshAll() {
    const [stats, daily, config, dupStats] = await Promise.all([
        api('/api/stats'), api('/api/stats/daily'), api('/api/config'), api('/api/duplicate/stats'),
    ]);
    if (stats) {
        setText('stat-leads', stats.total_leads || 0);
        setText('stat-sent', stats.total_sent || 0);
        setText('stat-opens', stats.opens || 0);
        setText('stat-hot', stats.hot_leads || 0);
        setText('stat-openrate', (stats.open_rate || 0) + '%');
        setText('stat-followups', stats.followups_sent || 0);
        if (stats.source_distribution) renderSourceStats(stats.source_distribution);
        const body = document.getElementById('recent-sent-body');
        if (body && stats.recent_sent?.length > 0) {
            body.innerHTML = stats.recent_sent.slice(0, 10).map(s => `
                <tr><td>${esc(s.email)}</td><td>${esc(s.company || '—')}</td>
                <td>${esc((s.subject || '').substring(0, 40))}</td><td>${fmtDate(s.sent_at)}</td>
                <td><button class="btn btn-sm btn-ghost" onclick="viewSentEmail('${esc(s.email)}')">👁</button></td></tr>
            `).join('');
        }
    }
    if (daily) {
        setText('daily-sent', daily.today_sent || 0);
        setText('daily-limit', daily.daily_limit || 80);
        setText('daily-pct', daily.percentage || 0);
        setText('daily-remaining', daily.remaining || 0);
        const fill = document.getElementById('daily-progress-fill');
        if (fill) fill.style.width = `${Math.min(daily.percentage || 0, 100)}%`;
    }
    if (dupStats) { setText('stat-dup-prevented', dupStats.duplicates_prevented || 0); }
    if (config) updateModeBadge();
    setText('last-update', `Son: ${new Date().toLocaleTimeString('tr-TR')}`);
}

function updateModeBadge() {
    const badge = document.getElementById('mode-badge');
    const text = document.getElementById('mode-text');
    if (badge) badge.className = 'mode-badge live';
    if (text) text.textContent = 'CANLI — AKTİF';
}

function renderSourceStats(dist) {
    const container = document.getElementById('source-stats');
    if (!container || !dist) return;
    const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]);
    if (entries.length === 0) { container.innerHTML = '<p class="text-muted">Kaynak verisi yok</p>'; return; }
    container.innerHTML = entries.map(([src, cnt]) => `
        <div class="source-stat" style="cursor:pointer" onclick="showLeadsBySource('${esc(src)}')">
            <div class="value">${cnt}</div><div class="label">${esc(src)}</div>
        </div>
    `).join('');
}

async function showLeadsBySource(source) {
    const data = await api(`/api/leads/source?source=${encodeURIComponent(source)}`);
    if (!data?.leads?.length) { showToast(`${source} kaynağında lead bulunamadı`, 'info'); return; }
    const rows = data.leads.slice(0, 50).map(l => `
        <tr><td>${esc(l.email)}</td><td>${esc(l.company||'—')}</td>
        <td>${esc(l.sector||'—')}</td><td>${esc(l.location||'—')}</td>
        <td>${l.score||0}</td></tr>
    `).join('');
    openModal(`📋 ${source} Kaynağından Leadler (${data.leads.length})`, `
        <table class="data-table" style="width:100%"><thead><tr>
            <th>Email</th><th>Şirket</th><th>Sektör</th><th>Lokasyon</th><th>Skor</th>
        </tr></thead><tbody>${rows}</tbody></table>
    `);
}

async function viewSentEmail(email) {
    const data = await api(`/api/sent/detail?email=${encodeURIComponent(email)}`);
    if (!data || data.error) {
        openModal('📧 Email Detay: ' + email, '<p>İçerik bulunamadı</p>');
        return;
    }
    const d = data;
    openModal('📧 Email Detay: ' + email, `
        <p><strong>Kime:</strong> ${esc(d.email||email)}</p>
        <p><strong>Şirket:</strong> ${esc(d.company||'—')}</p>
        <p><strong>Konu:</strong> ${esc(d.subject||d.chosen_subject||'—')}</p>
        <p><strong>QC Skor:</strong> ${d.qc_score||'—'}</p>
        <p><strong>Yöntem:</strong> ${esc(d.method||'—')}</p>
        <p><strong>Gönderim:</strong> ${fmtDate(d.sent_at)}</p>
        <hr>
        ${d.body_html || d.body_text || '<p>İçerik bulunamadı</p>'}
    `);
}

// ═══════════════════════════════════════════════════════════
// LEADS
// ═══════════════════════════════════════════════════════════
async function loadLeads(filter) {
    if (filter) currentLeadFilter = filter;
    const data = await api(`/api/leads?status=${currentLeadFilter}`);
    if (!data) return;
    leadsData = data.leads || [];
    setText('leads-count', data.count || 0);
    selectedLeads.clear(); updateSelectionButtons(); renderLeads();
}

function filterLeads(status) {
    currentLeadFilter = status;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    const btn = document.getElementById(`filter-${status}`);
    if (btn) btn.classList.add('active');
    loadLeads(status);
}

async function sendToUnsent() {
    if (!confirm('Tüm gönderilmemiş leadlere email göndermek istediğinize emin misiniz?')) return;
    // Unsent leadleri getir
    const data = await api('/api/leads?status=unsent');
    if (!data || !data.leads || data.leads.length === 0) {
        showToast('Gönderilmemiş lead bulunamadı', 'info');
        return;
    }
    const emails = data.leads.map(l => l.email || l.Email || '').filter(e => e);
    showToast(`${emails.length} gönderilmemiş lead seçildi, gönderiliyor...`, 'info');
    const result = await api('/api/leads/send-selected', 'POST', { emails });
    if (result) {
        showToast(`${result.sent || 0} email gönderildi!`, 'success');
        loadLeads();
    } else {
        showToast('Gönderim hatası', 'error');
    }
}

function renderLeads() {
    const body = document.getElementById('leads-body');
    if (!body) return;
    if (leadsData.length === 0) { body.innerHTML = '<tr><td colspan="9" class="empty-state">Lead bulunamadı</td></tr>'; return; }
    let sorted = [...leadsData];
    if (sortState.key) {
        sorted.sort((a, b) => {
            let va = a[sortState.key] || '', vb = b[sortState.key] || '';
            if (typeof va === 'number' && typeof vb === 'number') return sortState.dir === 'asc' ? va - vb : vb - va;
            va = String(va).toLowerCase(); vb = String(vb).toLowerCase();
            return sortState.dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
        });
    }
    body.innerHTML = sorted.map(l => {
        const email = l.email || l.Email || '';
        const score = l.ai_score || l.score || 0;
        const scoreClass = score >= 70 ? 'high' : score > 0 ? 'low' : '';
        const checked = selectedLeads.has(email) ? 'checked' : '';
        const statusMap = { sent: '<span class="agent-status ok">Gönderildi</span>', pending: '<span class="agent-status warning">Taslak</span>' };
        return `<tr class="${checked ? 'selected' : ''}">
            <td><input type="checkbox" ${checked} onchange="toggleLead('${esc(email)}', this)"></td>
            <td><strong>${esc(l.company || '—')}</strong></td>
            <td><a href="#" onclick="viewLeadDetail('${esc(email)}'); return false" style="color:var(--purple)">${esc(email)}</a></td>
            <td>${esc(l.sector || '—')}</td><td>${esc(l.location || '—')}</td>
            <td>${score > 0 ? `<span class="draft-score ${scoreClass}">${score}</span>` : '<span class="text-muted">—</span>'}</td>
            <td><span class="source-tag">${esc(l.source || 'csv')}</span></td>
            <td>${statusMap[l.send_status] || '<span class="agent-status">Yeni</span>'}</td>
            <td><button class="btn btn-sm btn-primary" onclick="previewDraft('${esc(email)}')" title="AI email taslağı">✍️</button>
                <button class="btn btn-sm btn-ghost" onclick="scoreSingleLead('${esc(email)}')" title="AI puanla">🔮</button></td>
        </tr>`;
    }).join('');
    document.querySelectorAll('.sortable').forEach(th => {
        th.classList.remove('asc', 'desc');
        if (th.dataset.sort === sortState.key) th.classList.add(sortState.dir);
    });
}

function sortLeads(key) {
    if (sortState.key === key) sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc';
    else { sortState.key = key; sortState.dir = 'asc'; }
    renderLeads();
}
function toggleLead(email, cb) { if (cb.checked) selectedLeads.add(email); else selectedLeads.delete(email); cb.closest('tr').classList.toggle('selected', cb.checked); updateSelectionButtons(); }
function toggleAllLeads(cb) { leadsData.forEach(l => { const e = l.email || l.Email || ''; if (cb.checked) selectedLeads.add(e); else selectedLeads.delete(e); }); renderLeads(); updateSelectionButtons(); }
function updateSelectionButtons() {
    const c = selectedLeads.size;
    const s = document.getElementById('btn-send-selected'), k = document.getElementById('btn-skip-selected'), p = document.getElementById('btn-preview-selected');
    if (s) { s.disabled = c === 0; s.textContent = c > 0 ? `Seçilenlere Gönder (${c})` : 'Seçilenlere Gönder'; }
    if (k) k.disabled = c === 0;
    if (p) p.disabled = c === 0;
}
// sendSelectedLeads + skipSelectedLeads — tek tanım aşağıda (L888+ civarı)

async function viewLeadDetail(email) {
    const lead = leadsData.find(l => (l.email || l.Email || '') === email);
    if (!lead) return;
    const draft = await api(`/api/sent/${encodeURIComponent(email)}/content`);
    const dc = draft?.draft_content || {};
    openModal(`👤 ${lead.company || email}`, `
        <div class="detail-grid">
            <span class="detail-label">Şirket</span><span class="detail-value">${esc(lead.company || '—')}</span>
            <span class="detail-label">Email</span><span class="detail-value">${esc(email)}</span>
            <span class="detail-label">Sektör</span><span class="detail-value">${esc(lead.sector || '—')}</span>
            <span class="detail-label">Konum</span><span class="detail-value">${esc(lead.location || '—')}</span>
            <span class="detail-label">Telefon</span><span class="detail-value">${esc(lead.phone || '—')}</span>
            <span class="detail-label">Website</span><span class="detail-value">${esc(lead.website || '—')}</span>
            <span class="detail-label">Kaynak</span><span class="detail-value"><span class="source-tag">${esc(lead.source || 'csv')}</span></span>
            <span class="detail-label">AI Skor</span><span class="detail-value">${lead.ai_score || '—'}</span>
            <span class="detail-label">Durum</span><span class="detail-value">${esc(lead.send_status || 'yeni')}</span>
        </div>
        ${dc.body_text ? `<div class="detail-section"><h4>📧 Son Email Taslağı</h4><p style="margin-bottom:8px"><strong>Konu:</strong> ${esc(dc.chosen_subject || '—')}</p><div class="email-content">${esc(dc.body_text)}</div></div>` : '<div class="detail-section"><p class="text-muted">Henüz email taslağı oluşturulmadı</p></div>'}
    `);
}

async function discoverLeads() {
    const sector = document.getElementById('discover-sector').value;
    const location = document.getElementById('discover-location').value;
    const status = document.getElementById('discover-status');
    status.className = 'discover-status active';
    status.innerHTML = '<span class="loading"></span> Lead keşfi yapılıyor... Bu birkaç dakika sürebilir.';
    showToast(`Lead keşfi: ${sector} / ${location}`, 'info');
    const data = await api('/api/leads/discover', 'POST', { sector, location });
    if (data && data.count > 0) {
        status.className = 'discover-status success';
        status.innerHTML = `✅ <strong>${data.count}</strong> lead keşfedildi!`;
        showToast(`${data.count} lead bulundu!`, 'success');
        const breakdown = document.getElementById('discover-source-breakdown');
        if (data.stats && breakdown) {
            const src = data.stats;
            const tags = [];
            if (src.directories_scraped > 0) tags.push(`Dizin: ${src.directories_scraped}`);
            if (src.telefoonboek_found > 0) tags.push(`Telefoonboek: ${src.telefoonboek_found}`);
            if (src.openstreetmap_found > 0) tags.push(`OSM: ${src.openstreetmap_found}`);
            if (src.mx_verified > 0) tags.push(`MX Doğru: ${src.mx_verified}`);
            breakdown.innerHTML = tags.map(t => `<span class="source-tag">${t}</span>`).join('');
        }
        loadLeads();
    } else { status.className = 'discover-status active'; status.innerHTML = '⚠️ Lead bulunamadı'; showToast('Lead bulunamadı', 'error'); }
}
async function scoreAllLeads() { showToast('Tüm leadler AI ile puanlanıyor...', 'info'); const d = await api('/api/leads/score', 'POST'); if (d?.scored) { showToast(`${d.scored} lead puanlandı`, 'success'); loadLeads(); } else showToast('Puanlama yapılamadı', 'error'); }
async function scoreSingleLead(email) { showToast(`${email} puanlanıyor...`, 'info'); const d = await api('/api/leads/score', 'POST'); if (d) { showToast('Puanlama tamamlandı', 'success'); loadLeads(); } }

async function previewDraft(email) {
    showToast('Claude AI email taslağı yazıyor...', 'info');
    const lead = leadsData.find(l => (l.email || l.Email) === email) || { email };
    const data = await api('/api/drafts/preview', 'POST', lead);
    if (data?.chosen_subject) {
        const sc = data.qc_score >= 90 ? 'high' : 'low';
        openModal(`✍️ Email Taslağı — ${email}`, `
            <div class="detail-grid">
                <span class="detail-label">Alıcı</span><span class="detail-value">${esc(email)}</span>
                <span class="detail-label">Şirket</span><span class="detail-value">${esc(lead.company || '—')}</span>
                <span class="detail-label">QC Skor</span><span class="detail-value"><span class="draft-score ${sc}">${data.qc_score}</span></span>
                <span class="detail-label">Revize</span><span class="detail-value">${data.auto_fix_retries || 0}</span>
                <span class="detail-label">Compliance</span><span class="detail-value">${data.compliance_ok ? '✅ OK' : '❌'}</span>
            </div>
            <div class="detail-section"><h4>📋 Konu Başlıkları (A/B/C)</h4><p>A: ${esc(data.subject_a || '—')}</p><p>B: ${esc(data.subject_b || '—')}</p><p>C: ${esc(data.subject_c || '—')}</p><p style="margin-top:8px"><strong>Seçilen:</strong> ${esc(data.chosen_subject)}</p></div>
            <div class="detail-section"><h4>📧 Email İçeriği</h4><div class="email-content">${esc(data.body_text || '')}</div></div>
        `);
        showToast(`QC: ${data.qc_score} — ${data.qc_score >= 90 ? 'Geçti ✅' : 'Düşük ⚠️'}`, data.qc_score >= 90 ? 'success' : 'error');
    } else showToast('Taslak oluşturulamadı', 'error');
}

// ═══════════════════════════════════════════════════════════
// GİDEN MAİLLER (YENİ)
// ═══════════════════════════════════════════════════════════
async function loadSentMails() {
    const [data, dupStats] = await Promise.all([api('/api/sent/all'), api('/api/duplicate/stats')]);
    if (data) {
        const emails = data.emails || [];
        setText('sent-total', data.count || 0);
        let openedCount = 0, repliedCount = 0;
        emails.forEach(e => { if (e.was_opened) openedCount++; if (e.response) repliedCount++; });
        setText('sent-opened', openedCount);
        setText('sent-replied', repliedCount);

        const body = document.getElementById('sentmails-body');
        if (body) {
            if (emails.length === 0) { body.innerHTML = '<tr><td colspan="8" class="empty-state">Henüz gönderim yok</td></tr>'; return; }
            body.innerHTML = emails.map(e => {
                const openBadge = e.was_opened ? '<span class="agent-status ok">✓ Açıldı</span>' : '<span class="text-muted">—</span>';
                const replyBadge = e.response ? `<span class="agent-status ok">${esc(e.response)}</span>` : '<span class="text-muted">—</span>';
                return `<tr>
                    <td>${fmtDate(e.sent_at)}</td>
                    <td><a href="#" onclick="viewSentEmail('${esc(e.email)}'); return false" style="color:var(--purple)">${esc(e.email)}</a></td>
                    <td>${esc(e.company || '—')}</td>
                    <td>${esc((e.chosen_subject || e.subject || '').substring(0, 45))}</td>
                    <td>${e.qc_score ? `<span class="draft-score ${e.qc_score >= 90 ? 'high' : 'low'}">${e.qc_score}</span>` : '—'}</td>
                    <td>${openBadge}</td><td>${replyBadge}</td>
                    <td><button class="btn btn-sm btn-ghost" onclick="viewSentEmail('${esc(e.email)}')">👁 İçerik</button></td>
                </tr>`;
            }).join('');
        }
    }
    if (dupStats) setText('sent-dup-blocked', dupStats.duplicates_prevented || 0);
}

// ═══════════════════════════════════════════════════════════
// FOLLOW-UP ENGINE (YENİ)
// ═══════════════════════════════════════════════════════════
async function loadFollowUpEngine() {
    const data = await api('/api/followups/all');
    if (!data) return;
    const stats = data.stats || {};
    setText('fu-total', stats.total || 0);
    setText('fu-pending', stats.pending || 0);
    setText('fu-sent', stats.sent || 0);
    setText('fu-cancelled', stats.cancelled || 0);

    // Step breakdown
    if (stats.steps) {
        setText('fu-step1-count', stats.steps.step_1?.sent || 0);
        setText('fu-step2-count', stats.steps.step_2?.sent || 0);
        setText('fu-step3-count', stats.steps.step_3?.sent || 0);
    }

    // Follow-up list
    const body = document.getElementById('followup-body');
    const followups = data.followups || [];
    if (body) {
        if (followups.length === 0) { body.innerHTML = '<tr><td colspan="7" class="empty-state">Henüz follow-up yok — kampanya başlattıktan sonra otomatik oluşturulur</td></tr>'; return; }
        body.innerHTML = followups.map(f => {
            const statusMap = { pending: '<span class="agent-status warning">Bekliyor</span>', sent: '<span class="agent-status ok">Gönderildi</span>', cancelled: '<span class="agent-status critical">İptal</span>' };
            return `<tr>
                <td>${esc(f.email)}</td>
                <td>${esc(f.lead_company || f.company || '—')}</td>
                <td><span class="source-tag">Aşama ${f.step || 1}</span></td>
                <td>${fmtDate(f.scheduled_at)}</td>
                <td>${statusMap[f.status] || `<span class="text-muted">${esc(f.status)}</span>`}</td>
                <td>${f.sent_at ? fmtDate(f.sent_at) : '—'}</td>
                <td><button class="btn btn-sm btn-ghost" onclick="viewFollowupDetail(${JSON.stringify(f).replace(/"/g, '&quot;')})">👁</button></td>
            </tr>`;
        }).join('');
    }
}

function viewFollowupDetail(f) {
    openModal(`🔄 Follow-Up — ${f.email}`, `
        <div class="detail-grid">
            <span class="detail-label">Email</span><span class="detail-value">${esc(f.email)}</span>
            <span class="detail-label">Şirket</span><span class="detail-value">${esc(f.lead_company || f.company || '—')}</span>
            <span class="detail-label">Aşama</span><span class="detail-value">Aşama ${f.step}</span>
            <span class="detail-label">Durum</span><span class="detail-value">${esc(f.status)}</span>
            <span class="detail-label">Planlanan</span><span class="detail-value">${fmtDate(f.scheduled_at)}</span>
            <span class="detail-label">Gönderildi</span><span class="detail-value">${f.sent_at ? fmtDate(f.sent_at) : '—'}</span>
        </div>
        ${f.subject ? `<div class="detail-section"><h4>Follow-Up Konu</h4><p>${esc(f.subject)}</p></div>` : ''}
        ${f.body_text ? `<div class="detail-section"><h4>İçerik</h4><div class="email-content">${esc(f.body_text)}</div></div>` : ''}
    `);
}

async function processFollowups() {
    showToast('Bekleyen follow-uplar işleniyor...', 'info');
    const d = await api('/api/followups/process', 'POST');
    if (d) { showToast(`${d.processed || 0} follow-up işlendi`, 'success'); loadFollowUpEngine(); }
}

// ═══════════════════════════════════════════════════════════
// CAMPAIGN
// ═══════════════════════════════════════════════════════════
async function startCampaign() {
    const limit = parseInt(document.getElementById('campaign-limit').value) || 80;
    showToast(`Kampanya başlatılıyor, limit: ${limit}`, 'info');
    const data = await api('/api/campaign/start', 'POST', { limit });
    if (data?.success) {
        showToast('Kampanya başladı', 'success');
        document.getElementById('btn-start-campaign').style.display = 'none';
        document.getElementById('btn-stop-campaign').style.display = 'inline-flex';
        document.getElementById('campaign-status-card').style.display = 'block';
        pollCampaignStatus();
    }
}

// toggleCampaignTestMode kaldırıldı (TEST_MODE artık yok)
async function stopCampaign() { await api('/api/campaign/stop', 'POST'); showToast('Kampanya durduruluyor...', 'info'); document.getElementById('btn-start-campaign').style.display = 'inline-flex'; document.getElementById('btn-stop-campaign').style.display = 'none'; }

async function loadCampaignStatus() {
    const [data, daily, cfg] = await Promise.all([api('/api/campaign/status'), api('/api/stats/daily'), api('/api/config')]);
    // Config yükle (test mode sync kaldırıldı)
    if (data?.running) { document.getElementById('btn-start-campaign').style.display = 'none'; document.getElementById('btn-stop-campaign').style.display = 'inline-flex'; document.getElementById('campaign-status-card').style.display = 'block'; }
    if (data?.stats) {
        const s = data.stats;
        const c = document.getElementById('campaign-stats');
        if (c) c.innerHTML = `
            <div class="campaign-stat-item"><div class="value">${s.total_leads||0}</div><div class="label">Toplam</div></div>
            <div class="campaign-stat-item"><div class="value">${s.processed||0}</div><div class="label">İşlenen</div></div>
            <div class="campaign-stat-item"><div class="value" style="color:var(--green)">${s.sent||0}</div><div class="label">Gönderilen</div></div>
            <div class="campaign-stat-item"><div class="value" style="color:var(--amber)">${s.skipped_compliance||0}</div><div class="label">Compliance</div></div>
            <div class="campaign-stat-item"><div class="value" style="color:var(--red)">${s.skipped_quality||0}</div><div class="label">QC Fail</div></div>
            <div class="campaign-stat-item"><div class="value" style="color:var(--red)">${s.failed||0}</div><div class="label">Hata</div></div>`;
    }
    if (daily) { setText('camp-today-sent', daily.today_sent || 0); setText('camp-remaining', daily.remaining || 0); }
}
function pollCampaignStatus() { const p = setInterval(async () => { const d = await api('/api/campaign/status'); if (!d?.running) { clearInterval(p); document.getElementById('btn-start-campaign').style.display = 'inline-flex'; document.getElementById('btn-stop-campaign').style.display = 'none'; showToast('Kampanya tamamlandı!', 'success'); } loadCampaignStatus(); }, 3000); }

async function bulkPreview() {
    const count = parseInt(document.getElementById('preview-count').value) || 5;
    showToast(`Claude AI ${count} email yazıyor...`, 'info');
    const data = await api('/api/drafts/bulk-preview', 'POST', { count });
    const container = document.getElementById('drafts-container');
    if (!container || !data) return;
    container.innerHTML = (data.drafts || []).map(d => {
        const sc = (d.qc_score || 0) >= 90 ? 'high' : 'low';
        const preview = (d.body_text || '').substring(0, 250);
        return `<div class="draft-card" onclick='viewDraftDetail(${JSON.stringify(d).replace(/'/g, "&#39;")})'>
            <div class="draft-header"><span><span class="draft-email">${esc(d.email)}</span></span><span class="draft-score ${sc}">QC: ${d.qc_score || 0}</span></div>
            <div class="draft-subject">${esc(d.chosen_subject || '—')}</div>
            <div class="draft-preview">${esc(preview)}${preview.length >= 250 ? '...' : ''}</div>
        </div>`;
    }).join('');
    showToast(`${data.count || 0} taslak üretildi — her biri şirkete özel`, 'success');
}
function viewDraftDetail(d) {
    openModal(`✍️ ${d.email}`, `
        <div class="detail-grid"><span class="detail-label">QC Skor</span><span class="detail-value"><span class="draft-score ${(d.qc_score||0)>=90?'high':'low'}">${d.qc_score||0}</span></span></div>
        <div class="detail-section"><h4>📋 Konu Başlıkları</h4><p>A: ${esc(d.subject_a || '—')}</p><p>B: ${esc(d.subject_b || '—')}</p><p>C: ${esc(d.subject_c || '—')}</p></div>
        <div class="detail-section"><h4>📧 İçerik</h4><div class="email-content">${esc(d.body_text || '')}</div></div>
    `);
}

// ═══════════════════════════════════════════════════════════
// AGENTS + SELF-IMPROVEMENT
// ═══════════════════════════════════════════════════════════
async function loadAgentStatus() {
    const [data, learningData] = await Promise.all([api('/api/agents/status'), api('/api/agents/learning')]);
    const grid = document.getElementById('agents-grid');
    if (grid && data) {
        grid.innerHTML = (data.agents || []).map(a => {
            const desc = AGENT_DESC[a.name] || '';
            const perf = learningData?.performance?.[a.name];
            const learningBadge = perf ? `<div class="agent-extra">📈 ${perf.learnings} öğrenme, ↑${perf.avg_improvement}% gelişme</div>` : '';
            return `<div class="agent-card" onclick="viewAgentDetail('${esc(a.name)}', '${esc(a.icon)}', '${esc(a.status)}')">
                <span class="agent-icon">${a.icon || '🤖'}</span>
                <div class="agent-info"><div class="agent-name">${esc(a.name)}</div><div class="agent-desc">${esc(desc.substring(0, 100))}...</div>${learningBadge}</div>
                <span class="agent-status ${(a.status || '').toLowerCase()}">${a.status}</span>
            </div>`;
        }).join('');
    }

    // Agent Learning Stats
    if (learningData?.performance) {
        const statsEl = document.getElementById('agent-learning-stats');
        if (statsEl) {
            const perf = learningData.performance;
            statsEl.innerHTML = Object.entries(perf).map(([name, p]) => `
                <div class="followup-stat"><div class="value">${p.learnings}</div><div class="label">${name}</div></div>
            `).join('') || '<p class="text-muted">Henüz öğrenme kaydı yok — sistem çalıştıkça otomatik birikir</p>';
        }
    }

    // Watchdog
    const watchdog = await api('/api/watchdog/status');
    const report = document.getElementById('watchdog-report');
    if (report && watchdog?.checks) {
        report.innerHTML = watchdog.checks.map(c => {
            const cls = c.status === 'OK' ? '' : c.status === 'WARNING' ? 'warning' : 'critical';
            return `<div class="watchdog-item ${cls}"><span>${esc(c.name)}: ${esc(c.detail || '')}</span><span class="agent-status ${cls || 'ok'}">${c.status}</span></div>`;
        }).join('');
    }
}

function viewAgentDetail(name, icon, status) {
    const desc = AGENT_DESC[name] || 'Detay bilgisi yok.';
    openModal(`${icon} ${name}`, `
        <div class="detail-grid">
            <span class="detail-label">Agent</span><span class="detail-value">${esc(name)}</span>
            <span class="detail-label">Durum</span><span class="detail-value"><span class="agent-status ${status.toLowerCase()}">${esc(status)}</span></span>
        </div>
        <div class="detail-section"><h4>📖 Ne Yapar?</h4><p style="line-height:1.7;color:var(--text-1)">${esc(desc)}</p></div>
        <div class="detail-section"><h4>💡 Feedback Ver</h4>
            <p class="text-muted">Bu agent'ın performansı hakkında geri bildirim verin — agent bundan öğrenir.</p>
            <textarea id="agent-feedback-text" style="width:100%;height:80px;background:rgba(255,255,255,0.03);border:1px solid var(--border);border-radius:var(--radius-xs);color:var(--text-0);padding:10px;font-family:inherit;font-size:13px;resize:vertical" placeholder="Örn: 'Email konuları daha kısa olmalı' veya 'Transport sektörüne daha teknik yaklaşım kullan'"></textarea>
            <button class="btn btn-primary btn-sm" style="margin-top:8px" onclick="submitAgentFeedback('${esc(name)}')">📤 Gönder</button>
        </div>
    `);
}

async function submitAgentFeedback(agentName) {
    const text = document.getElementById('agent-feedback-text')?.value;
    if (!text) { showToast('Feedback boş olamaz', 'error'); return; }
    const d = await api('/api/agents/feedback', 'POST', { agent_name: agentName, lesson: text, type: 'user_feedback', context: 'manual_input' });
    if (d?.success) { showToast(`${agentName} agent'ına feedback kaydedildi — öğrenme uygulanacak`, 'success'); closeModal(); }
    else showToast('Feedback kaydedilemedi', 'error');
}

async function loadAgentLearnings() {
    const d = await api('/api/agents/learning');
    if (!d) return;
    const learnings = d.learnings || [];
    if (learnings.length === 0) { showToast('Henüz öğrenme kaydı yok', 'info'); return; }
    openModal('📈 Agent Öğrenme Raporu', `
        <p class="text-muted">Agent'ların öğrenme geçmişi — kullanıcı feedbackleri ve otomatik öğrenmeler</p>
        <table style="margin-top:16px"><thead><tr><th>Agent</th><th>Tür</th><th>Öğrenme</th><th>Tarih</th></tr></thead>
        <tbody>${learnings.map(l => `<tr><td>${esc(l.agent_name)}</td><td><span class="source-tag">${esc(l.learning_type)}</span></td><td>${esc(l.lesson)}</td><td>${fmtDate(l.created_at)}</td></tr>`).join('')}</tbody></table>
    `);
}

// ═══════════════════════════════════════════════════════════
// AUTOMATION
// ═══════════════════════════════════════════════════════════
async function loadAutomationStatus() {
    const data = await api('/api/automation/status');
    if (!data) return;
    const indicator = document.getElementById('auto-indicator');
    const statusText = document.getElementById('auto-status-text');
    const actionText = document.getElementById('auto-action-text');
    const startBtn = document.getElementById('btn-start-auto');
    const stopBtn = document.getElementById('btn-stop-auto');
    if (data.running) {
        indicator.className = 'auto-indicator running'; statusText.textContent = 'Çalışıyor — Aktif';
        actionText.textContent = data.last_action || '...';
        startBtn.style.display = 'none'; stopBtn.style.display = 'inline-flex';
        setText('cycle-badge', `Cycle ${data.cycle || 0}`);
        setText('auto-last-cycle', data.last_cycle_at ? `Son: ${fmtDate(data.last_cycle_at)}` : 'Son: —');
        updatePipelineViz(data.last_action || '');
    } else {
        indicator.className = 'auto-indicator stopped'; statusText.textContent = 'Durdurulmuş';
        actionText.textContent = data.last_action || '—';
        startBtn.style.display = 'inline-flex'; stopBtn.style.display = 'none';
    }
}
function updatePipelineViz(action) {
    document.querySelectorAll('.pipeline-step').forEach(s => s.classList.remove('active', 'done'));
    const a = action.toLowerCase();
    let step = 0;
    if (a.includes('keşf')) step = 1; else if (a.includes('puanl')) step = 2;
    else if (a.includes('yaz') || a.includes('email')) step = 3;
    else if (a.includes('gönder') || a.includes('qc')) step = 4;
    else if (a.includes('follow')) step = 5;
    else if (a.includes('yanıt') || a.includes('tamamla')) step = 6;
    for (let i = 1; i < step; i++) { const el = document.getElementById(`pipe-step-${i}`); if (el) el.classList.add('done'); }
    const active = document.getElementById(`pipe-step-${step}`);
    if (active) active.classList.add('active');
}
async function startAutomation() { showToast('Otomasyon başlatılıyor...', 'info'); await api('/api/automation/start', 'POST'); showToast('Otomasyon aktif', 'success'); loadAutomationStatus(); startLogPolling(); }
async function stopAutomation() { await api('/api/automation/stop', 'POST'); showToast('Otomasyon durduruluyor...', 'info'); loadAutomationStatus(); stopLogPolling(); }
function startLogPolling() { stopLogPolling(); logRefreshInterval = setInterval(() => { loadLogs('automation-log'); loadAutomationStatus(); }, 5000); }
function stopLogPolling() { if (logRefreshInterval) { clearInterval(logRefreshInterval); logRefreshInterval = null; } }

// ═══════════════════════════════════════════════════════════
// RESPONSES
// ═══════════════════════════════════════════════════════════
async function loadResponses() {
    const [responses, followups] = await Promise.all([api('/api/responses'), api('/api/followups')]);
    if (responses) {
        const statsGrid = document.getElementById('response-stats-grid');
        if (statsGrid && responses.stats) {
            const cls = responses.stats.classifications || {};
            statsGrid.innerHTML = `
                <div class="stat-card gradient-2"><div class="stat-icon">🔥</div><div class="stat-info"><span class="stat-value">${cls.interested||0}</span><span class="stat-label">İlgili</span></div></div>
                <div class="stat-card gradient-3"><div class="stat-icon">❌</div><div class="stat-info"><span class="stat-value">${cls.not_interested||0}</span><span class="stat-label">İlgisiz</span></div></div>
                <div class="stat-card gradient-5"><div class="stat-icon">❓</div><div class="stat-info"><span class="stat-value">${cls.question||0}</span><span class="stat-label">Soru</span></div></div>
                <div class="stat-card gradient-6"><div class="stat-icon">🏖️</div><div class="stat-info"><span class="stat-value">${cls.out_of_office||0}</span><span class="stat-label">Ofis Dışı</span></div></div>`;
        }
        const hotBody = document.getElementById('hot-leads-body');
        if (hotBody && responses.hot_leads?.length > 0) {
            hotBody.innerHTML = responses.hot_leads.map(h => `<tr>
                <td>${esc(h.company || '—')}</td><td>${esc(h.email || '—')}</td>
                <td>${esc((h.response_summary || '').substring(0, 60))}</td>
                <td><span class="agent-status ok">${esc(h.classification || 'interested')}</span></td>
                <td>${fmtDate(h.classified_at)}</td>
                <td><button class="btn btn-sm btn-ghost" onclick="viewLeadDetail('${esc(h.email)}')">👁</button></td>
            </tr>`).join('');
        }
    }
    if (followups) {
        const c = document.getElementById('followup-stats');
        if (c) c.innerHTML = `<div class="followup-stats-grid">
            <div class="followup-stat"><div class="value">${followups.total||0}</div><div class="label">Toplam</div></div>
            <div class="followup-stat"><div class="value">${followups.pending||0}</div><div class="label">Bekleyen</div></div>
            <div class="followup-stat"><div class="value" style="color:var(--green)">${followups.sent||0}</div><div class="label">Gönderildi</div></div>
            <div class="followup-stat"><div class="value">${followups.cancelled||0}</div><div class="label">İptal</div></div>
        </div>`;
    }
}

// ═══════════════════════════════════════════════════════════
// SETTINGS (Sector Tags)
// ═══════════════════════════════════════════════════════════
async function loadSettings() {
    const data = await api('/api/config');
    if (!data) return;
    setVal('set-daily-limit', data.DAILY_SEND_LIMIT);
    setVal('set-delay-min', data.DELAY_MIN);
    setVal('set-delay-max', data.DELAY_MAX);
    setVal('set-human-review', data.HUMAN_REVIEW, 'checked');
    setVal('set-qc-min', data.QC_MIN_SCORE);
    setVal('set-target-location', data.TARGET_LOCATION);
    setVal('set-telefoonboek', data.TELEFOONBOEK_ENABLED, 'checked');
    setVal('set-openstreetmap', data.OPENSTREETMAP_ENABLED, 'checked');
    setVal('set-mx-verify', data.EMAIL_VERIFY_MX, 'checked');
    setVal('set-auto-start', data.AUTO_START, 'checked');
    setVal('set-auto-interval', data.AUTOMATION_INTERVAL);

    // Sector Tags
    const sectors = Array.isArray(data.SECTORS) ? data.SECTORS : (data.SECTORS || '').split(',').map(s => s.trim()).filter(Boolean);
    renderSectorTags(sectors);

    const anthStatus = document.getElementById('set-anthropic-status');
    if (anthStatus) { anthStatus.textContent = data.ANTHROPIC_KEY_SET ? '✅ Bağlı' : '❌ Ayarla'; anthStatus.className = `status-badge ${data.ANTHROPIC_KEY_SET ? 'ok' : 'error'}`; }
    const brevoStatus = document.getElementById('set-brevo-status');
    if (brevoStatus) { brevoStatus.textContent = data.BREVO_KEY_SET ? '✅ Bağlı' : '❌ Ayarla'; brevoStatus.className = `status-badge ${data.BREVO_KEY_SET ? 'ok' : 'error'}`; }
}

function renderSectorTags(sectors) {
    const container = document.getElementById('set-sectors-tags');
    if (!container) return;
    container.innerHTML = sectors.map(s => `<span class="sector-tag">${esc(s)}</span>`).join('');
}

async function saveSettings() {
    const data = {
        DAILY_SEND_LIMIT: parseInt(getVal('set-daily-limit')) || 80,
        DELAY_MIN: parseInt(getVal('set-delay-min')) || 25,
        DELAY_MAX: parseInt(getVal('set-delay-max')) || 55,
        HUMAN_REVIEW: getVal('set-human-review', 'checked'),
        QC_MIN_SCORE: parseInt(getVal('set-qc-min')) || 90,
        AUTO_START: getVal('set-auto-start', 'checked'),
        AUTOMATION_INTERVAL: parseInt(getVal('set-auto-interval')) || 15,
    };
    const result = await api('/api/config', 'PUT', data);
    if (result?.success) {
        showToast('Ayarlar kaydedildi ✅', 'success');
        updateModeBadge();
    }
    else showToast('Ayarlar kaydedilemedi', 'error');
}

function setVal(id, value, type = 'value') { const el = document.getElementById(id); if (!el) return; if (type === 'checked') el.checked = !!value; else el.value = value ?? ''; }
function getVal(id, type = 'value') { const el = document.getElementById(id); if (!el) return ''; return type === 'checked' ? el.checked : el.value; }

async function loadLogs(containerId = 'logs-container') {
    const data = await api('/api/logs');
    const container = document.getElementById(containerId);
    if (container && data?.logs) { container.textContent = data.logs.join(''); container.scrollTop = container.scrollHeight; }
}

// ─── AUTOMATION PIPELINE ───
let autoRefreshTimer = null;

async function startAutomation() {
    try {
        const res = await api('/api/automation/start', 'POST');
        // Accept any response that isn't explicitly an error
        if (res && !res?.error) {
            showToast(res?.message || 'Otomasyon başlatıldı', 'success');
            document.getElementById('btn-start-auto').style.display = 'none';
            document.getElementById('btn-stop-auto').style.display = '';
            updateModeBadge(true);
            if (autoRefreshTimer) clearInterval(autoRefreshTimer);
            autoRefreshTimer = setInterval(refreshAutomation, 5000);
            setTimeout(refreshAutomation, 1000);
        } else {
            showToast('Başlatılamadı: ' + (res?.error || JSON.stringify(res)), 'error');
        }
    } catch (e) {
        // Even on parse error, the server may have started — refresh to check
        showToast('Otomasyon başlatılıyor...', 'info');
        document.getElementById('btn-start-auto').style.display = 'none';
        document.getElementById('btn-stop-auto').style.display = '';
        updateModeBadge(true);
        if (autoRefreshTimer) clearInterval(autoRefreshTimer);
        autoRefreshTimer = setInterval(refreshAutomation, 5000);
        setTimeout(refreshAutomation, 2000);
    }
}

async function stopAutomation() {
    const res = await api('/api/automation/stop', 'POST');
    if (res?.ok) {
        showToast('Otomasyon durduruluyor...', 'info');
        document.getElementById('btn-start-auto').style.display = '';
        document.getElementById('btn-stop-auto').style.display = 'none';
        updateModeBadge(false);
        if (autoRefreshTimer) { clearInterval(autoRefreshTimer); autoRefreshTimer = null; }
    }
}

async function refreshAutomation() {
    const data = await api('/api/automation/status');
    if (!data) return;

    // Status text
    const statusEl = document.getElementById('auto-status-text');
    const actionEl = document.getElementById('auto-action-text');
    const indEl = document.getElementById('auto-indicator');
    if (statusEl) statusEl.textContent = data.running ? 'Çalışıyor' : 'Durdurulmuş';
    if (actionEl) actionEl.textContent = data.current_step || '—';
    if (indEl) { indEl.className = 'auto-indicator ' + (data.running ? 'running' : 'stopped'); }

    // Cycle info
    const cycleBadge = document.getElementById('cycle-badge');
    const lastCycle = document.getElementById('auto-last-cycle');
    if (cycleBadge) cycleBadge.textContent = 'Cycle ' + (data.cycle || 0);
    if (lastCycle) lastCycle.textContent = 'Son: ' + (data.last_cycle ? fmtDate(data.last_cycle) : '—');

    // Pipeline step indicators
    const stepNum = parseInt((data.current_step || '0').charAt(0)) || 0;
    for (let i = 1; i <= 6; i++) {
        const el = document.getElementById('pipe-step-' + i);
        if (el) {
            el.className = 'pipeline-step' + (i === stepNum ? ' active' : i < stepNum ? ' done' : '');
        }
    }

    // Buttons
    if (data.running) {
        document.getElementById('btn-start-auto').style.display = 'none';
        document.getElementById('btn-stop-auto').style.display = '';
    } else {
        document.getElementById('btn-start-auto').style.display = '';
        document.getElementById('btn-stop-auto').style.display = 'none';
    }

    // Logs
    const logEl = document.getElementById('automation-log');
    if (logEl && data.logs?.length > 0) {
        logEl.innerHTML = data.logs.map(l => `<div class="log-line">${esc(l)}</div>`).join('');
        logEl.scrollTop = logEl.scrollHeight;
    }

    // Mode badge
    updateModeBadge(data.running);

    // Stats in sidebar
    const stats = data.stats || {};
    setText('stat-leads', (stats.leads_found || 0) + ' keşfedildi');
}

function updateModeBadge(running) {
    const badge = document.getElementById('mode-badge');
    const text = document.getElementById('mode-text');
    if (badge) badge.className = 'mode-badge ' + (running ? 'live' : '');
    if (text) text.textContent = running ? 'CANLI — AKTİF' : 'DURDURULMUŞ';
}

function toggleSystemMode() {
    // Mode badge'e tıklayınca automation toggle
    const data = document.getElementById('auto-status-text');
    if (data && data.textContent === 'Çalışıyor') {
        stopAutomation();
    } else {
        startAutomation();
    }
}

// Load automation status on page load
document.addEventListener('DOMContentLoaded', () => {
    refreshAutomation();
});









// ─── PREVIEW SELECTED LEAD ───
async function previewSelectedLead() {
    if (selectedLeads.size === 0) { showToast('Önce lead seçin!', 'error'); return; }
    const email = Array.from(selectedLeads)[0];
    showToast('Email önizlemesi oluşturuluyor...', 'info');

    const data = await api('/api/campaign/preview', 'POST', { email });
    if (!data || data.error) {
        showToast('Önizleme oluşturulamadı: ' + (data?.error || 'Bilinmiyor'), 'error');
        return;
    }

    const modalContent = `<div style="padding:0">
        <div style="padding:12px 16px;background:var(--card-bg);border-bottom:1px solid var(--border)">
            <p><strong>Kime:</strong> ${esc(email)}</p>
            <p><strong>Şirket:</strong> ${esc(data.company || '-')}</p>
            <p><strong>Konu A:</strong> ${esc(data.subject_a || '-')}</p>
            <p><strong>Konu B:</strong> ${esc(data.subject_b || '-')}</p>
            <p><strong>Konu C:</strong> ${esc(data.subject_c || '-')}</p>
            <p><strong>Seçilen Konu:</strong> ${esc(data.chosen_subject || '-')}</p>
            <p><strong>QC Skor:</strong> ${data.qc_score || '-'}</p>
        </div>
        <div style="border:1px solid var(--border);border-radius:8px;margin:12px;background:#fff;overflow:hidden">
            ${data.body_html || '<p style="padding:20px">HTML içerik yok</p>'}
        </div>
        <div style="padding:12px 16px;display:flex;gap:8px;justify-content:flex-end;border-top:1px solid var(--border)">
            <button class="btn btn-sm btn-ghost" onclick="closeModal()">Vazgeç</button>
            <button class="btn btn-sm btn-primary" onclick="closeModal(); sendToSelected();">Onayla ve Gönder</button>
        </div>
    </div>`;

    openModal('Email Önizleme: ' + esc(email), modalContent);
}

// ─── PREVIEW DRAFT PER LEAD (✍️ button) ───
async function previewDraft(email) {
    showToast('Email taslağı oluşturuluyor...', 'info');
    const data = await api('/api/campaign/preview', 'POST', { email });
    if (!data || data.error) {
        showToast('Taslak oluşturulamadı: ' + (data?.error || 'Bilinmiyor'), 'error');
        return;
    }

    const modalContent = `<div style="padding:0">
        <div style="padding:12px 16px;background:var(--card-bg);border-bottom:1px solid var(--border)">
            <p><strong>Kime:</strong> ${esc(email)}</p>
            <p><strong>Şirket:</strong> ${esc(data.company || '-')}</p>
            <p><strong>Konu:</strong> ${esc(data.chosen_subject || data.subject_a || '-')}</p>
            <p><strong>QC Skor:</strong> ${data.qc_score || '-'}</p>
        </div>
        <div style="border:1px solid var(--border);border-radius:8px;margin:12px;background:#fff;overflow:hidden;max-height:500px;overflow-y:auto">
            ${data.body_html || '<p style="padding:20px">HTML içerik yok</p>'}
        </div>
        <div style="padding:12px 16px;display:flex;gap:8px;justify-content:flex-end;border-top:1px solid var(--border)">
            <button class="btn btn-sm btn-ghost" onclick="closeModal()">Vazgeç</button>
            <button class="btn btn-sm btn-primary" onclick="closeModal(); selectedLeads.clear(); selectedLeads.add('${esc(email)}'); sendToSelected();">Onayla ve Gönder</button>
        </div>
    </div>`;

    openModal('Email Taslağı: ' + esc(email), modalContent);
}

// ─── SEND TO SELECTED LEADS ───
// HTML onclick uses sendSelectedLeads — wrapper function
function sendSelectedLeads() { sendToSelected(); }

async function sendToSelected() {
    if (selectedLeads.size === 0) {
        showToast('Önce lead seçin!', 'error');
        return;
    }
    const emails = Array.from(selectedLeads);
    showToast(`${emails.length} lead'e email gönderiliyor...`, 'info');

    const data = await api('/api/campaign/send-selected', 'POST', { emails });
    if (data?.success) {
        showToast(`✅ ${data.sent || emails.length} email gönderildi!`, 'success');
        selectedLeads.clear();
        loadLeads();
    } else {
        showToast(`❌ Gönderim hatası: ${data?.error || 'bilinmiyor'}`, 'error');
    }
}

// ─── SKIP SELECTED LEADS ───
async function skipSelectedLeads() {
    if (selectedLeads.size === 0) { showToast('Önce lead seçin!', 'error'); return; }
    const emails = Array.from(selectedLeads);
    showToast(`${emails.length} lead atlanıyor...`, 'info');
    const data = await api('/api/leads/skip', 'POST', { emails });
    if (data) { showToast('Lead\'ler atlandı', 'success'); selectedLeads.clear(); loadLeads(); }
}

// ─── AGENT LEARNINGS ───
async function loadAgentLearnings() {
    const data = await api('/api/agents/learning');
    const container = document.getElementById('agent-learning-stats');
    if (!container) return;
    if (!data) { openModal('📈 Öğrenme Raporu', '<p>Henüz öğrenme verisi yok.</p>'); return; }
    const html = `<div style="padding:12px">
        <h4>Agent Öğrenme İstatistikleri</h4>
        <pre style="white-space:pre-wrap;font-size:0.85rem">${esc(JSON.stringify(data, null, 2))}</pre>
    </div>`;
    openModal('📈 Agent Öğrenme Raporu', html);
}

// ─── VIEW SENT EMAIL DETAIL ───
async function viewSentEmail(email) {
    const data = await api(`/api/sent/${encodeURIComponent(email)}/content`);
    if (data && !data.error) {
        openModal('📧 Email Detay: ' + (email || ''), `<div style="padding:12px">
            <p><strong>Kime:</strong> ${esc(email)}</p>
            <p><strong>Şirket:</strong> ${esc(data.company || '—')}</p>
            <p><strong>Konu:</strong> ${esc(data.subject || data.chosen_subject || '—')}</p>
            <p><strong>QC Skor:</strong> ${data.qc_score || '—'}</p>
            <p><strong>Yöntem:</strong> ${esc(data.method || '—')}</p>
            <p><strong>Gönderim:</strong> ${fmtDate(data.sent_at || '')}</p>
            <hr>
            ${data.body_html
                ? `<div style="border:1px solid #333;border-radius:8px;padding:16px;background:#1a1a2e">${data.body_html}</div>`
                : `<div style="white-space:pre-wrap;font-size:0.9rem">${esc(data.body_text || 'İçerik bulunamadı')}</div>`
            }
        </div>`);
    } else {
        showToast('Email detayı bulunamadı', 'error');
    }
}

// ─── SECTOR DROPDOWN & QUEUE ───
const SECTOR_COLORS = ['#06d6a0','#118ab2','#ef476f','#ffd166','#073b4c','#8338ec','#ff6b6b','#48bfe3','#4cc9f0','#7209b7','#f72585','#4361ee','#3a0ca3','#560bad','#b5179e','#f15bb5','#fee440','#00bbf9','#00f5d4','#9b5de5','#fb5607','#ff006e','#8ac926','#1982c4','#6a4c93','#f77f00','#0ead69'];

function initSectorUI() {
    api('/api/config').then(cfg => {
        if (!cfg) return;
        const sectors = cfg.SECTORS || [];
        // Dropdown doldur
        const sel = document.getElementById('discover-sector-select');
        if (sel) {
            sel.innerHTML = '<option value="">— Listeden seç veya aşağıya yaz —</option>';
            sectors.forEach((s, i) => {
                const opt = document.createElement('option');
                opt.value = s;
                opt.textContent = `${i + 1}. ${s}`;
                sel.appendChild(opt);
            });
        }
        // Queue chips
        const queue = document.getElementById('sector-queue');
        if (queue) {
            queue.innerHTML = sectors.map((s, i) => {
                const color = SECTOR_COLORS[i % SECTOR_COLORS.length];
                return `<span class="sector-chip" onclick="selectSector('${s}')" style="
                    display:inline-flex;align-items:center;gap:5px;padding:6px 14px;
                    border-radius:20px;cursor:pointer;font-size:13px;font-weight:500;
                    background:${color}22;color:${color};border:1px solid ${color}44;
                    transition:all .2s;
                " onmouseover="this.style.background='${color}44'" onmouseout="this.style.background='${color}22'">
                    <span style="background:${color};color:#fff;border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700">${i + 1}</span>
                    ${s}
                </span>`;
            }).join('');
        }
    });
}

function onSectorSelect(sel) {
    if (sel.value) {
        document.getElementById('discover-sector').value = sel.value;
    }
}

function selectSector(sector) {
    document.getElementById('discover-sector').value = sector;
    const sel = document.getElementById('discover-sector-select');
    if (sel) sel.value = sector;
    showToast(`Sektör seçildi: ${sector}`, 'info');
}

// ─── UTILITY ───
function setText(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }
function esc(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function fmtDate(d) { if (!d) return '—'; try { return new Date(d).toLocaleDateString('tr-TR', {day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}); } catch { return d; } }

// ═══ REAL-TIME SOCKET.IO ═══
let socket = null;
function initSocketIO() {
    if (typeof io === 'undefined') {
        console.warn('Socket.IO not loaded — falling back to polling');
        return;
    }
    try {
        socket = io({ transports: ['websocket', 'polling'] });
        socket.on('connect', () => {
            console.log('🔌 Real-time bağlantı aktif');
            const badge = document.getElementById('mode-badge');
            if (badge) badge.title = 'Real-time aktif';
        });
        socket.on('disconnect', () => console.warn('🔌 Real-time bağlantı kesildi'));

        // ─── Lead bulunduğunda dashboard anında güncelle ───
        socket.on('leads_updated', (data) => {
            console.log('📡 Lead güncellendi:', data);
            loadDashboard();
            showToast(`${data.count || 0} yeni lead bulundu`, 'success');
        });

        // ─── Otomasyon durumu değiştiğinde ───
        socket.on('automation_update', (data) => {
            console.log('⚙️ Otomasyon:', data);
            loadAutomationStatus();
            if (data.action) {
                const el = document.getElementById('auto-action-text');
                if (el) el.textContent = data.action;
            }
        });

        // ─── Kampanya bittiğinde ───
        socket.on('campaign_finished', (data) => {
            console.log('🏁 Kampanya tamamlandı:', data);
            loadDashboard();
            loadCampaignStatus();
            showToast('✅ Kampanya tamamlandı!', 'success');
        });

        // ─── Email taslağı oluşturulduğunda ───
        socket.on('draft_generated', (data) => {
            console.log('📝 Taslak:', data);
            loadCampaignStatus();
        });

        // ─── Brevo event (open, click, bounce) ───
        socket.on('brevo_event', (data) => {
            console.log('📧 Brevo event:', data);
            loadDashboard();
        });

        // ─── Leads keşfedildiğinde ───
        socket.on('leads_discovered', (data) => {
            console.log('🔍 Lead keşfedildi:', data);
            loadDashboard();
            if (data.count > 0) {
                showToast(`🔍 ${data.count} yeni lead keşfedildi!`, 'success');
            }
        });

        // ─── Email gönderildiğinde ───
        socket.on('email_sent', (data) => {
            console.log('📤 Email gönderildi:', data);
            loadDashboard();
        });

    } catch (e) {
        console.warn('Socket.IO init hatası:', e);
    }
}

// ═══════════════════════════════════════════════════════════
// AGENT TOPLANTI ODASI
// ═══════════════════════════════════════════════════════════
let meetingActive = false;
let meetingPollInterval = null;
let meetingMessages = [];

const AGENT_ICONS = {
    'Orchestrator': '/img/agent_orchestrator.png',
    'AI Copywriter': '/img/agent_copywriter.png',
    'AI Quality Control': '/img/agent_quality.png',
    'Lead Scorer': '/img/agent_scorer.png',
    'Recon Agent': '/img/agent_recon.png',
    'Lead Finder': '/img/agent_finder.png',
    'Follow-Up Engine': '/img/agent_followup.png',
    'Response Tracker': '/img/agent_tracker.png',
    'Watchdog': '/img/agent_watchdog.png',
    'Compliance (AVG)': '/img/agent_compliance.png',
    'A/B Test Engine': '/img/agent_abtest.png'
};

// ═══ 3D DEPTH SCALING — Y pozisyonuna göre boyut ayarla ═══
function applyDepthScaling(seat) {
    const top = parseInt(seat.style.top || getComputedStyle(seat).top) || 0;
    seat.classList.remove('depth-far', 'depth-mid', 'depth-near', 'depth-front');
    if (top < 150)      seat.classList.add('depth-far');
    else if (top < 350) seat.classList.add('depth-mid');
    else if (top < 550) seat.classList.add('depth-near');
    else                seat.classList.add('depth-front');
}

// ═══ DIRECTION DETECTION — yürürken hangi yöne bak ═══
function detectDirection(seat, targetClass) {
    // Get current position
    const rect = seat.getBoundingClientRect();
    const currentLeft = rect.left;

    // Determine target side (table is in the center ~48%)
    const office = document.getElementById('meeting-office');
    const officeCenter = office ? office.getBoundingClientRect().width / 2 : 600;

    seat.classList.remove('facing-left', 'facing-right');
    if (targetClass === 'at-table') {
        // Walking to table — face toward center
        if (currentLeft > officeCenter) {
            seat.classList.add('facing-left');
        } else {
            seat.classList.add('facing-right');
        }
    } else {
        // Walking back to desk — face away from center
        if (currentLeft > officeCenter) {
            seat.classList.add('facing-right');
        } else {
            seat.classList.add('facing-left');
        }
    }
}

async function startAgentMeeting() {
    showToast('Agent toplantısı başlatılıyor...', 'info');
    const d = await api('/api/agents/meeting', 'POST', { action: 'start' });
    if (d?.success) {
        meetingActive = true;
        meetingMessages = [];
        document.getElementById('meeting-status-badge').textContent = 'CANLI';
        document.getElementById('meeting-status-badge').classList.add('active');
        document.getElementById('btn-start-meeting').style.display = 'none';
        document.getElementById('btn-stop-meeting').style.display = 'inline-flex';
        document.getElementById('meeting-chat-stream').innerHTML = '';

        // ── Toplantı masasını aktifleştir
        document.querySelector('.meeting-table')?.classList.add('active');

        // ── Agent'ları sırayla masaya yürüt (3D aware)
        const seats = document.querySelectorAll('.meeting-seat');
        seats.forEach((seat, i) => {
            // 1) Direction detection — önce yönü belirle
            setTimeout(() => {
                detectDirection(seat, 'at-table');
                seat.classList.remove('idle', 'at-desk');
                seat.classList.add('walking');
            }, i * 350);

            // 2) Masaya otur — walking dur, depth güncelle
            setTimeout(() => {
                seat.classList.remove('walking', 'facing-left', 'facing-right');
                seat.classList.add('at-table');
                applyDepthScaling(seat);
            }, i * 350 + 2000);
        });

        showToast('Toplantı başladı — agent\'lar toplanıyor...', 'success');

        // Tüm agent'lar oturduktan sonra mesajları göster
        const totalWalkTime = seats.length * 350 + 2800;
        setTimeout(() => {
            if (d.messages && d.messages.length > 0) {
                displayMeetingMessages(d.messages);
            }
        }, totalWalkTime);

        // Yeni mesajları polling ile getir
        meetingPollInterval = setInterval(pollMeetingMessages, 8000);
    } else {
        showToast('Toplantı başlatılamadı', 'error');
    }
}

function stopAgentMeeting() {
    meetingActive = false;
    if (meetingPollInterval) { clearInterval(meetingPollInterval); meetingPollInterval = null; }
    document.getElementById('meeting-status-badge').textContent = 'Bitti';
    document.getElementById('meeting-status-badge').classList.remove('active');
    document.getElementById('btn-start-meeting').style.display = 'inline-flex';
    document.getElementById('btn-stop-meeting').style.display = 'none';

    // Konuşanları durdur
    document.querySelectorAll('.meeting-seat.speaking').forEach(s => s.classList.remove('speaking'));
    document.getElementById('speech-bubbles-overlay').innerHTML = '';

    // ── Toplantı masasını deaktif et
    document.querySelector('.meeting-table')?.classList.remove('active');

    // ── Agent'ları sırayla masalarına geri yürüt (3D aware)
    const seats = document.querySelectorAll('.meeting-seat');
    seats.forEach((seat, i) => {
        setTimeout(() => {
            detectDirection(seat, 'at-desk');
            seat.classList.remove('at-table');
            seat.classList.add('walking');
        }, i * 250);

        setTimeout(() => {
            seat.classList.remove('walking', 'facing-left', 'facing-right');
            seat.classList.add('at-desk', 'idle');
            applyDepthScaling(seat);
        }, i * 250 + 2000);
    });

    showToast('Toplantı sona erdi — agent\'lar masalarına dönüyor', 'info');
}

async function pollMeetingMessages() {
    if (!meetingActive) return;
    const d = await api('/api/agents/meeting', 'POST', { action: 'continue', offset: meetingMessages.length });
    if (d?.messages && d.messages.length > 0) {
        displayMeetingMessages(d.messages);
    }
    if (d?.finished) {
        stopAgentMeeting();
    }
}

function displayMeetingMessages(messages) {
    const stream = document.getElementById('meeting-chat-stream');
    const overlay = document.getElementById('speech-bubbles-overlay');

    messages.forEach((msg, idx) => {
        meetingMessages.push(msg);

        // Delayed display for dramatic effect
        setTimeout(() => {
            // 1. Chat stream message
            const chatEl = document.createElement('div');
            chatEl.className = 'chat-msg';
            const iconSrc = AGENT_ICONS[msg.agent] || '';
            const avatarHtml = iconSrc ? `<img src="${iconSrc}" alt="${esc(msg.agent)}">` : '🤖';
            const time = new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
            chatEl.innerHTML = `
                <div class="chat-msg-avatar">${avatarHtml}</div>
                <div class="chat-msg-content">
                    <div class="chat-msg-header">
                        <span class="chat-msg-name">${esc(msg.agent)}</span>
                        <span class="chat-msg-time">${time}</span>
                    </div>
                    <div class="chat-msg-text">${esc(msg.text)}</div>
                </div>`;
            stream.appendChild(chatEl);
            stream.scrollTop = stream.scrollHeight;

            // 2. Highlight speaking agent seat
            document.querySelectorAll('.meeting-seat.speaking').forEach(s => s.classList.remove('speaking'));
            const seat = document.querySelector(`.meeting-seat[data-agent="${msg.agent}"]`);
            if (seat) {
                seat.classList.add('speaking');

                // 3. Speech bubble near the agent
                overlay.innerHTML = '';
                const bubble = document.createElement('div');
                bubble.className = 'speech-bubble';
                const truncText = msg.text.length > 80 ? msg.text.substring(0, 80) + '...' : msg.text;
                bubble.innerHTML = `<div class="bubble-agent">${esc(msg.agent)}</div>${esc(truncText)}`;

                // Position near the seat
                const seatRect = seat.getBoundingClientRect();
                const officeRect = document.getElementById('meeting-office').getBoundingClientRect();
                const bX = seatRect.left - officeRect.left + 30;
                const bY = seatRect.top - officeRect.top - 60;
                bubble.style.left = Math.max(10, Math.min(bX, officeRect.width - 220)) + 'px';
                bubble.style.top = Math.max(5, bY) + 'px';
                overlay.appendChild(bubble);

                // Clear bubble after delay
                setTimeout(() => { if (bubble.parentNode) bubble.remove(); }, 6000);
            }

        }, idx * 2500);
    });
}

// ═══ OFFICE INIT — Agent'ları ofiste masalarına yerleştir ═══
function initOfficeAgents() {
    document.querySelectorAll('.meeting-seat').forEach(seat => {
        seat.classList.add('at-desk', 'idle');
        // Apply initial depth scaling
        setTimeout(() => applyDepthScaling(seat), 100);
    });

    // Spawn ambient floating particles
    const particleContainer = document.getElementById('office-particles');
    if (particleContainer) {
        for (let i = 0; i < 20; i++) {
            const p = document.createElement('div');
            p.className = 'particle';
            p.style.left = Math.random() * 100 + '%';
            p.style.bottom = Math.random() * 30 + '%';
            p.style.animationDelay = Math.random() * 8 + 's';
            p.style.animationDuration = (6 + Math.random() * 6) + 's';
            const colors = ['rgba(124,92,252,0.5)', 'rgba(0,214,143,0.4)', 'rgba(100,149,237,0.4)'];
            p.style.background = colors[Math.floor(Math.random() * colors.length)];
            p.style.width = (2 + Math.random() * 3) + 'px';
            p.style.height = p.style.width;
            particleContainer.appendChild(p);
        }
    }

    // Random subtle idle movements — agents fidget at desks
    setInterval(() => {
        if (meetingActive) return;
        const seats = document.querySelectorAll('.meeting-seat.idle');
        const randomSeat = seats[Math.floor(Math.random() * seats.length)];
        if (randomSeat) {
            const jitterX = (Math.random() - 0.5) * 6;
            const jitterY = (Math.random() - 0.5) * 4;
            randomSeat.style.transform = `translate(${jitterX}px, ${jitterY}px)`;
            setTimeout(() => { randomSeat.style.transform = ''; }, 2000);
        }
    }, 3000);
}

// ═══ INIT ═══
document.addEventListener('DOMContentLoaded', () => {
    refreshAll();
    initSocketIO();
    initSectorUI();
    initOfficeAgents();
    // Socket.IO aktifse daha az polling (60s), değilse 30s
    autoRefreshInterval = setInterval(refreshAll, socket ? 60000 : 30000);
});
