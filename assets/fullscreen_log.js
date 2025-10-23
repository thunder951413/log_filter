/**
 * 日志过滤结果全屏显示功能
 * 当页面滚动到底部时，将日志过滤结果放大到全页面大小，并添加过渡动画
 */

// 等待页面完全加载
function waitForElement(elementId, callback, maxAttempts = 50, interval = 200) {
    let attempts = 0;
    
    function checkElement() {
        attempts++;
        const element = document.getElementById(elementId);
        
        if (element) {
            callback(element);
        } else if (attempts < maxAttempts) {
            setTimeout(checkElement, interval);
        } else {
            console.error(`无法找到元素: ${elementId}`);
        }
    }
    
    checkElement();
}

// 初始化全屏日志功能
function initFullscreenLog() {
    // 获取日志过滤结果容器
    waitForElement('log-filter-results', function(logResultsContainer) {
        console.log('找到日志过滤结果容器，初始化全屏功能');
        
        // 创建全屏显示的容器
        const fullscreenContainer = document.createElement('div');
        fullscreenContainer.id = 'fullscreen-log-container';
        fullscreenContainer.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: white;
            z-index: 9999;
            padding: 20px;
            box-sizing: border-box;
            overflow: auto;
            transform: translateY(100%);
            transition: transform 0.5s ease-in-out;
            display: none;
        `;
        
        // 创建关闭按钮
        const closeButton = document.createElement('button');
        closeButton.innerHTML = '退出全屏';
        closeButton.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            background-color: #007bff;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 10px 15px;
            cursor: pointer;
            font-size: 14px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        `;
        
        // 创建全屏内容的容器
        const fullscreenContent = document.createElement('div');
        fullscreenContent.style.cssText = `
            width: 100%;
            height: 100%;
            overflow: auto;
            padding-top: 50px;
            box-sizing: border-box;
            font-family: monospace;
            font-size: 14px;
            white-space: pre-wrap;
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 5px;
            padding: 20px;
        `;
        
        // 组装全屏容器
        fullscreenContainer.appendChild(closeButton);
        fullscreenContainer.appendChild(fullscreenContent);
        document.body.appendChild(fullscreenContainer);
        
        // 关闭按钮点击事件
        closeButton.addEventListener('click', exitFullscreen);
        
        // ESC键退出全屏
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && fullscreenContainer.style.display === 'block') {
                exitFullscreen();
            }
        });
        
        // 滚动事件监听
        let isScrolling = false;
        let scrollTimeout;
        let lastScrollTop = 0;
        let scrollDirection = 'down'; // 默认向下滚动
        let wasAtBottom = false; // 标记上一次是否已经到达底部
        const SCROLL_THRESHOLD = 10; // 滚动阈值，避免微小滚动误判
        
        window.addEventListener('scroll', function() {
            if (!isScrolling) {
                window.requestAnimationFrame(function() {
                    checkScrollPosition();
                    isScrolling = false;
                });
                isScrolling = true;
            }
            
            // 清除之前的超时
            clearTimeout(scrollTimeout);
            
            // 设置新的超时
            scrollTimeout = setTimeout(function() {
                isScrolling = false;
            }, 66); // 大约每15帧检查一次
        });
        
        // 检查滚动位置
        function checkScrollPosition() {
            // 如果已经在全屏模式，不检查
            if (fullscreenContainer.style.display === 'block') {
                return;
            }
            
            // 获取当前滚动位置
            const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
            const windowHeight = window.innerHeight;
            const documentHeight = document.documentElement.scrollHeight;
            const scrollDistance = Math.abs(scrollTop - lastScrollTop);
            
            // 检查是否在底部附近
            const isAtBottom = scrollTop + windowHeight >= documentHeight - 100;
            
            // 只有当滚动距离超过阈值时才更新方向
            if (scrollDistance > SCROLL_THRESHOLD) {
                // 判断滚动方向
                if (scrollTop > lastScrollTop) {
                    scrollDirection = 'down';
                } else {
                    scrollDirection = 'up';
                }
                
                // 更新最后滚动位置
                lastScrollTop = scrollTop <= 0 ? 0 : scrollTop;
            }
            
            // 只有在向下滚动且接近底部且之前不在底部时才触发全屏
            if (scrollDirection === 'down' && isAtBottom && !wasAtBottom) {
                // 确保日志结果容器有内容
                if (logResultsContainer.innerHTML.trim() !== '') {
                    enterFullscreen();
                }
            }
            
            // 更新是否在底部的状态
            wasAtBottom = isAtBottom;
        }
        
        // 进入全屏模式
        function enterFullscreen() {
            // 复制日志内容到全屏容器
            fullscreenContent.innerHTML = logResultsContainer.innerHTML;
            
            // 显示全屏容器
            fullscreenContainer.style.display = 'block';
            
            // 触发重排以确保过渡效果生效
            void fullscreenContainer.offsetWidth;
            
            // 应用过渡动画
            fullscreenContainer.style.transform = 'translateY(0)';
            
            // 滚动到全屏容器的顶部
            fullscreenContainer.scrollTop = 0;
            
            // 防止页面滚动
            document.body.style.overflow = 'hidden';
        }
        
        // 退出全屏模式
        function exitFullscreen() {
            // 应用过渡动画
            fullscreenContainer.style.transform = 'translateY(100%)';
            
            // 动画完成后隐藏容器
            setTimeout(function() {
                fullscreenContainer.style.display = 'none';
                // 恢复页面滚动
                document.body.style.overflow = '';
            }, 500); // 与CSS过渡时间相匹配
        }
        
        // 窗口大小变化时调整全屏容器
        window.addEventListener('resize', function() {
            if (fullscreenContainer.style.display === 'block') {
                // 可以在这里添加响应式调整逻辑
            }
        });
        
        console.log('日志全屏显示功能已初始化');
    });
}

// 尝试立即初始化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFullscreenLog);
} else {
    // 如果DOM已经加载完成，延迟一点时间再初始化，确保Dash组件已经渲染
    setTimeout(initFullscreenLog, 1000);
}