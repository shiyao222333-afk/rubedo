// 诊断工具 - 同步加载，页面渲染前立即可用
// 不依赖 window.dp，直接从 DOM 读取实际渲染高度
window.showDiag = function() {
    var cal = document.getElementById('calendar');
    if (!cal) { alert('找不到 #calendar 元素'); return; }

    // 读取容器高度
    var containerH = cal.offsetHeight;

    // 读取 DayPilot 实际渲染的内部元素高度
    // DayPilot Lite 渲染结构：#calendar > div（内部容器，包含表头和网格）
    var innerEl = cal.firstElementChild;
    var actualGridH = '?';
    if (innerEl && innerEl.offsetHeight > 0) {
        actualGridH = innerEl.offsetHeight;
        // 如果第一个子元素只是表头（40px左右），找它的子元素或下一个兄弟
        if (actualGridH <= 50) {
            // 可能是表头，找包含网格的父元素
            var gridEl = cal.querySelector('[class*="scroll"]')
                      || cal.querySelector('[class*="body"]')
                      || cal.querySelector('[class*="grid"]');
            if (gridEl) actualGridH = gridEl.offsetHeight + (innerEl.offsetHeight || 0);
        }
    }
    // 兜底：用 scrollHeight（包含溢出内容）
    if (actualGridH === '?' || actualGridH < 100) {
        actualGridH = cal.scrollHeight || '?';
    }

    // 读取 DayPilot 配置（如果可用）
    // DayPilot Lite 属性可能在 dp 上，也可能在 dp.config 上
    var dp = window.dp;
    var cellH = '?';
    var headerH = '?';
    var dpHeight = '?';
    var gridFromConfig = '?';

    if (dp) {
        // 尝试多种可能的属性路径
        cellH = (dp.cellHeight !== undefined) ? dp.cellHeight
              : (dp.config && dp.config.cellHeight !== undefined) ? dp.config.cellHeight
              : '?';
        headerH = (dp.headerHeight !== undefined) ? dp.headerHeight
                : (dp.config && dp.config.headerHeight !== undefined) ? dp.config.headerHeight
                : '?';
        dpHeight = (dp.height !== undefined) ? JSON.stringify(dp.height)
                 : (dp.config && dp.config.height !== undefined) ? JSON.stringify(dp.config.height)
                 : '?';
        if (cellH !== '?' && headerH !== '?') {
            gridFromConfig = cellH * 48 + headerH;
        }
    }

    // 真正的「可见空白」= 面板真实顶部 − 日历底边缘（视口坐标）
    // 面板真实顶部 = 视口高度 − 面板实际高度（不要用写死 280，否则最大化后算错）
    var panelTopReal = '?';
    if (panelEl) {
        panelTopReal = window.innerHeight - panelEl.offsetHeight;
    }
    var calBottomReal = '?';
    if (cal) {
        var cr = cal.getBoundingClientRect();
        calBottomReal = cr.bottom;
    }
    var gap = (calBottomReal !== '?' ) ? (panelTopReal - calBottomReal) : '?';

    var mainEl = document.querySelector('.main-layout');
    var panelEl = document.getElementById('detail-panel');

    // 读取底部面板覆盖（fillBlank）的诊断数据
    var fb = window.__fillBlank;
    var fbStatus = fb
        ? (fb.applied ? ('已盖住 ' + fb.blank + 'px 空白') : '无需覆盖（无空白）')
        : '未运行（请先等待页面加载）';

    var rows = [
        ['视口高度 (window.innerHeight)', window.innerHeight + 'px'],
        ['main-layout 高度', (mainEl ? mainEl.offsetHeight : '?') + 'px'],
        ['#calendar 容器高度', containerH + 'px'],
        ['#detail-panel 高度', (panelEl ? panelEl.offsetHeight : '?') + 'px'],
        ['DayPilot 实际渲染高度', actualGridH + 'px'],
        ['DayPilot cellHeight', cellH + 'px'],
        ['DayPilot headerHeight', headerH + 'px'],
        ['网格理论高度 (cellH×48+header)', gridFromConfig + 'px'],
        ['可见空白 (面板顶−日历底)', gap + 'px'],
        ['DayPilot config.height', dpHeight],
        ['── 底部面板覆盖状态 ──', fbStatus],
        ['FillBlank 日历底边缘', fb ? fb.calBottom + 'px' : '?'],
        ['FillBlank 面板顶部', fb ? fb.panelTop + 'px' : '?'],
        ['FillBlank 计算空白', fb ? fb.blank + 'px' : '?'],
        ['FillBlank 面板高度', fb ? fb.panelH + 'px' : '?'],
        ['window.dp 状态', dp ? '✅ 已设置' : '❌ 未设置'],
    ];

    var html = '<table style="width:100%;border-collapse:collapse;font-size:13px;">';
    html += '<tr><th style="text-align:left;padding:4px 8px;border-bottom:1px solid #0f3460;">项目</th>';
    html += '<th style="text-align:left;padding:4px 8px;border-bottom:1px solid #0f3460;">值</th></tr>';

    rows.forEach(function(r) {
        var val = parseInt(r[1]);
        var cls = '';
        var style = '';
        if (r[0].indexOf('空白') >= 0 && val !== '?' && !isNaN(val)) {
            if (val > 10) { cls = 'bad'; style = 'color:#e94560;font-weight:bold;'; }
            else if (val < -10) { cls = 'warn'; style = 'color:#ffa500;font-weight:bold;'; }
            else { cls = 'ok'; style = 'color:#4CAF50;'; }
        }
        if (r[0].indexOf('dp 状态') >= 0) {
            style = r[1].indexOf('✅') >= 0 ? 'color:#4CAF50;' : 'color:#e94560;';
        }
        html += '<tr>';
        html += '<td style="padding:4px 8px;border-bottom:1px solid #16213e;">' + r[0] + '</td>';
        html += '<td style="padding:4px 8px;border-bottom:1px solid #16213e;' + style + '">' + r[1] + '</td>';
        html += '</tr>';
    });
    html += '</table>';
    html += '<p style="margin-top:12px;color:#aaa;font-size:12px;">';
    html += '💡 可见空白 > 10px → 底部面板没盖住日历底（检查 .main-layout 是否溢出视口 / 面板高度是否够）<br>';
    html += '可见空白 < -10px → 面板盖住了日历底部（窗口态正常现象，面板顶在日历底之上）';
    html += '</p>';

    var body = document.getElementById('diag-body');
    if (body) body.innerHTML = html;
    var overlay = document.getElementById('diag-overlay');
    if (overlay) overlay.classList.add('show');
};

window.copyDiag = function() {
    var el = document.getElementById('diag-body');
    if (!el) { alert('请先运行诊断'); return; }
    var text = el.innerText || el.textContent;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function() {
            alert('✅ 已复制到剪贴板');
        }).catch(function() {
            var ta = document.createElement('textarea');
            ta.value = text;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
            alert('✅ 已复制');
        });
    } else {
        var ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        alert('✅ 已复制');
    }
};

// 快捷键：Ctrl+Shift+D 打开诊断，Esc 关闭
document.addEventListener('keydown', function(e) {
    if (e.ctrlKey && e.shiftKey && e.key === 'D') {
        e.preventDefault();
        if (window.showDiag) window.showDiag();
    }
    if (e.key === 'Escape') {
        var overlay = document.getElementById('diag-overlay');
        if (overlay) overlay.classList.remove('show');
    }
});
