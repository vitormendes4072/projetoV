// --- 1. Password field restore ---
document.addEventListener("DOMContentLoaded", function() {
    const serverNewPass = SETTINGS_INIT.serverNewPass;
    const serverConfirmPass = SETTINGS_INIT.serverConfirmPass;

    if (serverNewPass) {
        const newInput = document.getElementById('new_pass_input');
        if (newInput) newInput.value = serverNewPass;
    }
    if (serverConfirmPass) {
        const confirmInput = document.getElementById('confirm_pass_input');
        if (confirmInput) confirmInput.value = serverConfirmPass;
    }
});

// --- 2. Tax regime suggestion with toast ---
const regimeSelect = document.getElementById('tax_regime');
const taxInput = document.getElementById('default_tax_rate');

function showToast(msg) {
    const toast = document.getElementById('toast');
    const msgEl = document.getElementById('toast-message');
    msgEl.innerText = msg;

    toast.classList.remove('hidden');
    setTimeout(() => {
        toast.classList.remove('translate-x-full', 'opacity-0');
    }, 10);

    setTimeout(closeToast, 8000);
}

function closeToast() {
    const toast = document.getElementById('toast');
    toast.classList.add('translate-x-full', 'opacity-0');
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 500);
}

if (regimeSelect && taxInput) {
    regimeSelect.addEventListener('change', function() {
        const regime = this.value;
        let sugestao = "";

        if (regime === 'mei') {
            taxInput.value = 0.0;
            sugestao = "Para MEI, a alíquota sobre venda é 0% (você paga apenas o DAS fixo mensal). Ajustamos para zero automaticamente.";
        } else if (regime === 'simples') {
            sugestao = "O Simples Nacional começa em 4.0% para Comércio (Anexo I). Verifique em qual faixa de faturamento sua empresa está.";
        } else if (regime === 'presumido') {
            taxInput.value = 5.93;
            sugestao = "Definimos 5.93% (Federais). Lembre-se de somar o ICMS do seu estado (ex: 18%) neste campo para o cálculo ficar correto.";
        } else if (regime === 'real') {
            taxInput.value = 9.25;
            sugestao = "Definimos 9.25% (PIS/COFINS). Não se esqueça de adicionar o ICMS no valor total.";
        }

        if (sugestao) showToast(sugestao);
    });
}

// --- 3. Modal logic ---
const profileModal = document.getElementById('securityModal');
const profilePassInput = document.getElementById('current_password');

function openModal() {
    profileModal.classList.remove('hidden');
    profileModal.classList.add('flex');
    setTimeout(() => { if(profilePassInput) profilePassInput.focus(); }, 100);
}
function closeModal() {
    profileModal.classList.add('hidden');
    profileModal.classList.remove('flex');
    if(profilePassInput) profilePassInput.value = '';
}

const passModal = document.getElementById('passwordModal');
const passInput = document.getElementById('modal_current_password');
const newPassInput = document.getElementById('new_pass_input');
const confirmPassInput = document.getElementById('confirm_pass_input');
const errorNew = document.getElementById('js_error_new');
const errorConfirm = document.getElementById('js_error_confirm');

function forceOpenPasswordModal() {
    passModal.classList.remove('hidden');
    passModal.classList.add('flex');
    setTimeout(() => { if(passInput) passInput.focus(); }, 100);
}

function validateAndOpenPasswordModal() {
    errorNew.classList.add('hidden');
    errorConfirm.classList.add('hidden');
    newPassInput.classList.remove('border-red-500');
    confirmPassInput.classList.remove('border-red-500');

    let isValid = true;
    const newPass = newPassInput.value;
    const confirmPass = confirmPassInput.value;

    if (newPass.length < 8) {
        errorNew.innerText = "A senha deve ter pelo menos 8 caracteres.";
        errorNew.classList.remove('hidden');
        newPassInput.classList.add('border-red-500');
        isValid = false;
    }
    if (newPass !== confirmPass) {
        errorConfirm.innerText = "As senhas não conferem.";
        errorConfirm.classList.remove('hidden');
        confirmPassInput.classList.add('border-red-500');
        isValid = false;
    }

    if (!isValid) return;
    forceOpenPasswordModal();
}

function closePasswordModal() {
    passModal.classList.add('hidden');
    passModal.classList.remove('flex');
    if(passInput) passInput.value = '';
}

window.onclick = function(event) {
    if (event.target == profileModal) closeModal();
    if (event.target == passModal) closePasswordModal();
}

if (SETTINGS_INIT.openProfileModal) openModal();
if (SETTINGS_INIT.openPasswordModal) forceOpenPasswordModal();

// ================= AMAZON SP-API =================

async function amzFetchJSON(url, options = {}) {
    const res = await fetch(url, {
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        ...options
    });

    let body = null;
    try { body = await res.json(); } catch (e) {}

    if (!res.ok) {
        const msg = (body && body.error) ? body.error : `Erro ${res.status}`;
        throw new Error(msg);
    }
    return body;
}

function setAmzResult(msg, type="info") {
    const el = document.getElementById("amz_result");
    if (!el) return;

    const base = "rounded-lg border p-3";
    if (type === "success") el.className = base + " border-green-200 bg-green-50 text-green-800";
    else if (type === "error") el.className = base + " border-red-200 bg-red-50 text-red-800";
    else el.className = base + " border-slate-200 bg-slate-50 text-slate-700";

    el.textContent = msg;
}

async function loadAmazonStatus() {
    try {
        const data = await amzFetchJSON("/integrations/amazon/status", { method: "GET" });

        const statusEl = document.getElementById("amz_status");
        const lastSyncEl = document.getElementById("amz_last_sync");
        const hintEl = document.getElementById("amz_status_hint");

        if (!data.connected) {
            statusEl.textContent = "Não conectado";
            statusEl.className = "text-red-600 font-bold";
            lastSyncEl.textContent = "—";
            hintEl.textContent = "Preencha as credenciais e clique em Salvar.";
            return;
        }

        statusEl.textContent = "Conectado";
        statusEl.className = "text-green-700 font-bold";
        lastSyncEl.textContent = data.last_sync_at ? data.last_sync_at : "—";
        hintEl.textContent = `Marketplace: ${data.marketplace_id || "—"}`;
    } catch (e) {
        const statusEl = document.getElementById("amz_status");
        if (statusEl) {
            statusEl.textContent = "Erro ao carregar status";
            statusEl.className = "text-red-600 font-bold";
        }
    }
}

function getAmazonPayload() {
    return {
        marketplace_id: document.getElementById("amz_marketplace_id")?.value?.trim(),
        seller_id: document.getElementById("amz_seller_id")?.value?.trim() || null,

        lwa_client_id: document.getElementById("amz_lwa_client_id")?.value?.trim(),
        lwa_client_secret: document.getElementById("amz_lwa_client_secret")?.value,
        lwa_refresh_token: document.getElementById("amz_lwa_refresh_token")?.value,

        aws_access_key_id: document.getElementById("amz_aws_access_key_id")?.value?.trim(),
        aws_secret_access_key: document.getElementById("amz_aws_secret_access_key")?.value,
        aws_region: document.getElementById("amz_aws_region")?.value?.trim() || "us-east-1",
        role_arn: document.getElementById("amz_role_arn")?.value?.trim() || null,
    };
}

async function onAmazonSave() {
    try {
        setAmzResult("Salvando credenciais...", "info");
        const payload = getAmazonPayload();
        await amzFetchJSON("/integrations/amazon/connect", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        setAmzResult("Credenciais salvas com sucesso.", "success");
        await loadAmazonStatus();
    } catch (e) {
        setAmzResult(`Falha ao salvar: ${e.message}`, "error");
    }
}

async function onAmazonTest() {
    try {
        setAmzResult("Testando conexão (últimos 2 dias)...", "info");
        const data = await amzFetchJSON("/integrations/amazon/test", { method: "POST" });
        setAmzResult(`Conexão OK. Pedidos encontrados: ${data.orders_found}`, "success");
    } catch (e) {
        setAmzResult(`Falha no teste: ${e.message}`, "error");
    }
}

async function pollJob(jobId, maxWaitMs = 300_000, intervalMs = 2_000) {
    const deadline = Date.now() + maxWaitMs;
    let tick = 0;

    while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, intervalMs));
        tick++;

        const res = await fetch(
            `/integrations/amazon/jobs/${encodeURIComponent(jobId)}`,
            { headers: { "X-CSRFToken": csrfToken } }
        );
        const data = await res.json();

        if (!res.ok || !data.ok) {
            throw new Error(data.error || `Erro ao verificar job (HTTP ${res.status})`);
        }

        const status = data.status;

        if (status === "queued" || status === "scheduled") {
            setAmzResult(`Na fila… aguardando worker (${tick * intervalMs / 1000}s)`, "info");

        } else if (status === "started") {
            setAmzResult(`Sincronizando com a Amazon… (${tick * intervalMs / 1000}s)`, "info");

        } else if (status === "finished") {
            return data.result || {};

        } else if (status === "failed") {
            throw new Error(data.error || "O job falhou sem mensagem de erro.");

        } else {
            setAmzResult(`Status desconhecido: ${status}`, "info");
        }
    }

    throw new Error(
        "Timeout: o sync está demorando mais que 5 minutos. " +
        "Verifique se o worker RQ está em execução."
    );
}

async function onAmazonSync() {
    try {
        setAmzResult("Enfileirando sync completo (30 dias)…", "info");

        const queued = await amzFetchJSON("/integrations/amazon/sync_full?days=30", { method: "POST" });

        if (!queued.job_id) {
            throw new Error(queued.error || "Resposta inesperada: sem job_id");
        }

        setAmzResult(`Job enfileirado (${queued.job_id.slice(0, 8)}…). Aguardando worker…`, "info");

        const result = await pollJob(queued.job_id);

        setAmzResult(
            `Sync concluído. ` +
            `Pedidos: ${result.orders ?? "?"} | ` +
            `Itens: ${result.items ?? "?"} | ` +
            `Eventos financeiros: ${result.financial_events ?? "?"}`,
            "success"
        );
        await loadAmazonStatus();

    } catch (e) {
        setAmzResult(`Falha na sync: ${e.message}`, "error");
    }
}

async function onAmazonMock() {
    try {
        const orderId = prompt("Digite o AmazonOrderId para inserir o mock:", "702-1234567-1234567");
        if (!orderId) return;

        setAmzResult("Inserindo mock de eventos financeiros (DEV)...", "info");

        const res = await fetch(`/integrations/amazon/dev/mock_finances?order_id=${encodeURIComponent(orderId)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });

        const text = await res.text();
        if (!res.ok) {
            throw new Error(text);
        }

        let data = null;
        try { data = JSON.parse(text); } catch (e) { data = { raw: text }; }

        setAmzResult(`Mock inserido com sucesso. inserted=${data.inserted || "?"}`, "success");
    } catch (e) {
        setAmzResult(`Falha ao inserir mock: ${e.message}`, "error");
    }
}

async function onAmazonMockProducts() {
    try {
        setAmzResult("Criando produtos mock (DEV)...", "info");

        const res = await fetch("/integrations/amazon/dev/mock_products", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({})
        });

        const text = await res.text();
        if (!res.ok) throw new Error(text);

        let data = null;
        try { data = JSON.parse(text); } catch { data = { raw: text }; }

        setAmzResult(`Produtos mock criados/atualizados. upserted=${data.upserted || "?"}`, "success");
    } catch (e) {
        setAmzResult(`Falha ao criar produtos mock: ${e.message}`, "error");
    }
}

document.addEventListener("DOMContentLoaded", function () {
    const btnSave = document.getElementById("btn_amz_save");
    const btnTest = document.getElementById("btn_amz_test");
    const btnSync = document.getElementById("btn_amz_sync");
    const btnMock = document.getElementById("btn_amz_mock");

    if (btnSave) btnSave.addEventListener("click", onAmazonSave);
    if (btnTest) btnTest.addEventListener("click", onAmazonTest);
    if (btnSync) btnSync.addEventListener("click", onAmazonSync);
    if (btnMock) btnMock.addEventListener("click", onAmazonMock);

    const btnMockProducts = document.getElementById("btn_amz_mock_products");
    if (btnMockProducts) btnMockProducts.addEventListener("click", onAmazonMockProducts);

    loadAmazonStatus();
});
