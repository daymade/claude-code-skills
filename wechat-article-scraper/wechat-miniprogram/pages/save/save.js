const app = getApp();

Page({
  data: {
    url: '',
    title: '',
    saving: false,
    saveResult: null,
    error: null,
    progress: 0
  },

  onLoad(options) {
    // Handle share message from WeChat
    if (options.url) {
      this.setData({
        url: decodeURIComponent(options.url),
        title: decodeURIComponent(options.title || '')
      });
      this.saveArticle();
    }
  },

  // Handle user input URL
  onUrlInput(e) {
    this.setData({ url: e.detail.value });
  },

  // Handle user input title
  onTitleInput(e) {
    this.setData({ title: e.detail.value });
  },

  // Save article
  async saveArticle() {
    const { url, title, saving } = this.data;

    if (!url) {
      wx.showToast({ title: '请输入链接', icon: 'none' });
      return;
    }

    if (saving) return;

    this.setData({ saving: true, error: null, progress: 0 });

    try {
      // Get login code
      const loginRes = await wx.login();

      // Start saving
      const response = await new Promise((resolve, reject) => {
        wx.request({
          url: `${app.globalData.apiBaseUrl}/api/wechat/miniapp/save`,
          method: 'POST',
          header: {
            'Content-Type': 'application/json'
          },
          data: {
            url,
            title,
            code: loginRes.code
          },
          success: resolve,
          fail: reject
        });
      });

      if (response.statusCode === 200) {
        const data = response.data;

        if (data.duplicate) {
          this.setData({
            saving: false,
            saveResult: data,
            progress: 100
          });
          wx.showToast({ title: '已在收藏中', icon: 'success' });

          // Navigate to article
          setTimeout(() => {
            wx.navigateTo({
              url: `/pages/article/article?id=${data.articleId}`
            });
          }, 1000);
        } else {
          // Poll for status
          this.setData({
            saveResult: data,
            progress: 30
          });
          this.pollJobStatus(data.jobId);
        }
      } else {
        throw new Error(response.data?.error || '保存失败');
      }

    } catch (error) {
      this.setData({
        saving: false,
        error: error.message || '保存失败，请重试'
      });
      wx.showToast({ title: error.message || '保存失败', icon: 'error' });
    }
  },

  // Poll job status
  async pollJobStatus(jobId) {
    const maxAttempts = 30;
    let attempts = 0;

    const checkStatus = async () => {
      if (attempts >= maxAttempts) {
        this.setData({
          saving: false,
          error: '保存超时，请稍后查看'
        });
        return;
      }

      attempts++;

      try {
        const response = await new Promise((resolve, reject) => {
          wx.request({
            url: `${app.globalData.apiBaseUrl}/api/wechat/miniapp/save?jobId=${jobId}`,
            method: 'GET',
            success: resolve,
            fail: reject
          });
        });

        if (response.statusCode === 200) {
          const data = response.data;

          if (data.status === 'completed') {
            this.setData({
              saving: false,
              progress: 100,
              saveResult: {
                ...this.data.saveResult,
                ...data.result
              }
            });
            wx.showToast({ title: '保存成功', icon: 'success' });

            // Navigate to article
            if (data.result?.articleId) {
              setTimeout(() => {
                wx.navigateTo({
                  url: `/pages/article/article?id=${data.result.articleId}`
                });
              }, 1000);
            }
          } else if (data.status === 'failed') {
            this.setData({
              saving: false,
              error: data.error || '保存失败'
            });
            wx.showToast({ title: '保存失败', icon: 'error' });
          } else {
            // Still processing
            this.setData({
              progress: Math.min(30 + attempts * 2, 90)
            });
            setTimeout(checkStatus, 2000);
          }
        }
      } catch (error) {
        this.setData({
          saving: false,
          error: '状态查询失败'
        });
      }
    };

    setTimeout(checkStatus, 2000);
  },

  // Navigate to article list
  goToList() {
    wx.switchTab({
      url: '/pages/index/index'
    });
  },

  // Manual retry
  retry() {
    this.saveArticle();
  }
});
