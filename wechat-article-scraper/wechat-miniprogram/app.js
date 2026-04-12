App({
  globalData: {
    userInfo: null,
    apiBaseUrl: 'https://api.wechat-scraper.com'
  },

  onLaunch() {
    // Check login status
    const token = wx.getStorageSync('token');
    if (!token) {
      this.login();
    }
  },

  login() {
    wx.login({
      success: (res) => {
        if (res.code) {
          // Send code to backend
          wx.request({
            url: `${this.globalData.apiBaseUrl}/api/wechat/miniapp/login`,
            method: 'POST',
            data: { code: res.code },
            success: (response) => {
              if (response.data.token) {
                wx.setStorageSync('token', response.data.token);
                wx.setStorageSync('userId', response.data.userId);
              }
            }
          });
        }
      }
    });
  }
});
