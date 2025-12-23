(function() {
    // 标记是否正在同步中，防止循环触发
    var isSyncing = false;

    // 检查是否启用了同步滚动
    function isSyncEnabled() {
        var checkbox = document.querySelector('#compare-sync-scroll-switch input[type="checkbox"]');
        return checkbox ? checkbox.checked : true; // 默认启用
    }

    // 绑定同步滚动事件
    function bindSyncScroll() {
        var left = document.getElementById('compare-diff-left');
        var right = document.getElementById('compare-diff-right');

        if (!left || !right) return;

        // 检查是否已经绑定过 (防止重复绑定)
        if (left.getAttribute('data-sync-bound') === 'true' && right.getAttribute('data-sync-bound') === 'true') {
            return;
        }

        console.log('Binding sync scroll events...');

        function syncScroll(source, target) {
            if (isSyncing) return;
            if (!isSyncEnabled()) return;

            isSyncing = true;
            
            // 同步 scrollTop 和 scrollLeft
            if (Math.abs(target.scrollTop - source.scrollTop) > 1) {
                target.scrollTop = source.scrollTop;
            }
            if (Math.abs(target.scrollLeft - source.scrollLeft) > 1) {
                target.scrollLeft = source.scrollLeft;
            }

            // 使用 requestAnimationFrame 或 setTimeout 来重置标志
            // 稍微延时以确保滚动事件处理完成
            setTimeout(function() {
                isSyncing = false;
            }, 50);
        }

        // 左侧滚动 -> 同步右侧
        left.onscroll = function() {
            syncScroll(left, right);
        };

        // 右侧滚动 -> 同步左侧
        right.onscroll = function() {
            syncScroll(right, left);
        };

        // 标记已绑定
        left.setAttribute('data-sync-bound', 'true');
        right.setAttribute('data-sync-bound', 'true');
    }

    // 使用 MutationObserver 监听 DOM 变化
    // 当对比结果被插入 DOM 时，自动绑定事件
    var observer = new MutationObserver(function(mutations) {
        var shouldBind = false;
        for (var i = 0; i < mutations.length; i++) {
            var mutation = mutations[i];
            if (mutation.type === 'childList') {
                // 检查是否有相关元素被添加
                if (document.getElementById('compare-diff-left')) {
                    shouldBind = true;
                    break;
                }
            }
        }
        
        if (shouldBind) {
            // 稍等一下确保 DOM 完全就绪
            setTimeout(bindSyncScroll, 100);
        }
    });

    // 开始观察 document.body
    document.addEventListener('DOMContentLoaded', function() {
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
        
        // 初始绑定尝试
        setTimeout(bindSyncScroll, 500);
    });

    // 如果脚本加载时 DOM 已经就绪（例如 Dash 更新时重新加载脚本）
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
        setTimeout(bindSyncScroll, 500);
    }

})();

