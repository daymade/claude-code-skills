const app = getApp();

Page({
  data: {
    articles: [],
    loading: false,
    hasMore: true,
    page: 1,
    pageSize: 20,
    userInfo: null
  },

  onLoad() {
    this.loadArticles();
    this.getUserInfo();
  },

  onPullDownRefresh() {
    this.setData({ page: 1, articles: [], hasMore: true });
    this.loadArticles().then(() => {
      wx.stopPullDownRefresh();
    });
  },

  onReachBottom() {
    if (this.data.hasMore && !this.data.loading) {
      this.loadArticles();
    }
  },

  // Get user info
  getUserInfo() {
    const userId = wx.getStorageSync('userId');
    if (userId) {
      this.setData({ userInfo: { id: userId } });
    }
  },

  // Load saved articles
  async loadArticles() {
    if (this.data.loading) return;

    this.setData({ loading: true });

    try {
      const token = wx.getStorageSync('token');
      const response = await new Promise((resolve, reject) => {
        wx.request({
          url: `${app.globalData.apiBaseUrl}/api/articles`,
          method: 'GET',
          header: {
            'Authorization': `Bearer ${token}`
          },
          data: {
            page: this.data.page,
            pageSize: this.data.pageSize
          },
          success: resolve,
          fail: reject
        });
      });

      if (response.statusCode === 200) {
        const data = response.data;
        const newArticles = this.data.page === 1 ? data.articles : [...this.data.articles, ...data.articles];

        this.setData({
          articles: newArticles,
          hasMore: data.articles.length >= this.data.pageSize,
          page: this.data.page + 1
        });
      }
    } catch (error) {
      wx.showToast({ title: '加载失败', icon: 'error' });
    } finally {
      this.setData({ loading: false });
    }
  },

  // Navigate to article detail
  openArticle(e) {
    const { id } = e.currentTarget.dataset;
    wx.navigateTo({
      url: `/pages/article/article?id=${id}`
    });
  },

  // Search articles
  onSearch() {
    wx.navigateTo({
      url: '/pages/search/search'
    });
  },

  // Navigate to save page
  goToSave() {
    wx.switchTab({
      url: '/pages/save/save'
    });
  }
});
