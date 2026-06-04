var TOKEN = localStorage.getItem("token");
var USER = JSON.parse(localStorage.getItem("user") || "{}");

var ROLE_NAMES = {
    admin: "系统管理员", applicant: "申请人", dept_supervisor: "部门主管",
    studio_manager: "演播厅主管", executor: "执行管理员"
};

function roleName(r) { return ROLE_NAMES[r] || r; }

async function api(url, options) {
    var opts = options || {};
    if (!opts.headers) opts.headers = {};
    if (TOKEN) opts.headers["Authorization"] = "Bearer " + TOKEN;
    if (!opts.headers["Content-Type"] && !(opts.body instanceof FormData)) opts.headers["Content-Type"] = "application/json";
    if (typeof opts.body === "object" && !(opts.body instanceof FormData)) opts.body = JSON.stringify(opts.body);
    var res = await fetch(url, opts);
    if (res.status === 401) { localStorage.clear(); window.location.href = "/login"; throw new Error("Unauthorized"); }
    if (!res.ok) { var err = await res.json().catch(function(){return {detail:"Request failed"}}); throw new Error(err.detail || "Request failed"); }
    return res.json();
}

async function apiForm(url, body) {
    var res = await fetch(url, { method: "POST", headers: { "Authorization": "Bearer " + TOKEN }, body: body });
    if (res.status === 401) { localStorage.clear(); window.location.href = "/login"; throw new Error("Unauthorized"); }
    if (!res.ok) { var err = await res.json().catch(function(){return {detail:"Request failed"}}); throw new Error(err.detail || "Request failed"); }
    return res.json();
}

async function apiDel(url) {
    var res = await fetch(url, { method: "DELETE", headers: { "Authorization": "Bearer " + TOKEN } });
    if (res.status === 401) { localStorage.clear(); window.location.href = "/login"; throw new Error("Unauthorized"); }
    if (!res.ok) { var err = await res.json().catch(function(){return {detail:"Request failed"}}); throw new Error(err.detail || "Request failed"); }
    return res.json();
}

function logout() { localStorage.clear(); window.location.href = "/login"; }

function showToast(msg, type) {
    type = type || "success";
    var colors = { success: "bg-green-600", error: "bg-red-600", info: "bg-blue-600" };
    var toast = document.createElement("div");
    toast.className = "fixed top-4 right-4 " + colors[type] + " text-white px-6 py-3 rounded-lg shadow-lg z-50 font-semibold";
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(function(){ toast.remove(); }, 3000);
}

function formatTime(t) { if (!t) return ""; return t.replace("T", " ").substring(0, 16); }

var STATUS_MAP = {
    pending: { label: "待部门审批", cls: "badge-pending" },
    dept_approved: { label: "待终审", cls: "badge-info" },
    dept_rejected: { label: "部门驳回", cls: "badge-rejected" },
    studio_approved: { label: "待分配", cls: "badge-info" },
    studio_rejected: { label: "终审驳回", cls: "badge-rejected" },
    assigned: { label: "已分配", cls: "badge-info" },
    completed: { label: "待报告", cls: "badge-pending" },
    reported: { label: "已完成", cls: "badge-approved" }
};

function statusBadge(s) {
    var m = STATUS_MAP[s] || { label: s, cls: "badge-pending" };
    return "<span class=\"badge " + m.cls + "\">" + m.label + "</span>";
}

function initSidebar() {
    if (USER.real_name) {
        var n = document.getElementById("sidebar-name");
        var a = document.getElementById("avatar-letter");
        var r = document.getElementById("sidebar-role");
        if (n) n.textContent = USER.real_name;
        if (a) a.textContent = USER.real_name[0];
        if (r) r.textContent = (USER.roles || []).map(function(x){return roleName(x)}).join(" / ");
        if (USER.roles && (USER.roles.indexOf("admin") >= 0 || USER.roles.indexOf("executor") >= 0)) {
            var al = document.getElementById("admin-links");
            if (al) al.classList.remove("hidden");
        }
    }
    var p = window.location.pathname;
    document.querySelectorAll("[data-nav]").forEach(function(el) {
        if (el.dataset.nav === p.split("/").filter(Boolean).join("-") || false) {
            el.classList.add("active");
        }
    });
    document.querySelectorAll("[data-tab]").forEach(function(el) {
        if (p === "/" + el.dataset.tab || (p.startsWith("/admin/") && el.dataset.tab === "admin")) {
            el.classList.add("active");
        }
    });
}
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initSidebar);
} else {
    initSidebar();
}
