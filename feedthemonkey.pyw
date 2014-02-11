#!/usr/bin/env python2

import sys, os, json, tempfile, urllib2, urllib, json, ctypes
from PyQt4 import QtGui, QtCore, QtWebKit, QtNetwork
from threading import Thread
from sys import platform as _platform

myappid = 'jabs.nu.feedthemonkey.2' # arbitrary string
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid) # permet la modification de l'icone WIN7

settings = QtCore.QSettings(".\\feedthemonkey.ini", QtCore.QSettings.IniFormat)

iconApp = "png/feedmonkey.png"
iconMark = "png/mark_set.png"
iconMarkSet = "png/mark_set.png"
iconMarkUnset = "png/mark_unset.png"
iconPub = "png/pub_set.png"
iconPubSet = "png/pub_set.png"
iconPubUnset = "png/pub_unset.png"

class MainWindow(QtGui.QMainWindow):
  def __init__(self):
    QtGui.QMainWindow.__init__(self)
    self.setWindowIcon(QtGui.QIcon(iconApp))
    self.addAction(QtGui.QAction("Full Screen", self, checkable=True, toggled=lambda v: self.showFullScreen() if v else self.showNormal(), shortcut="F11"))
    self.history = self.get("history", [])
    self.restoreGeometry(QtCore.QByteArray.fromRawData(settings.value("geometry").toByteArray()))
    self.restoreState(QtCore.QByteArray.fromRawData(settings.value("state").toByteArray()))

    self.initUI()

    session_id = self.get("session_id")
    server_url = self.get("server_url")

    if not (session_id and server_url):
      self.authenticate()
    else:
      self.initApp()

  def initUI(self):
    self.list = List(self)
    self.content = Content(self)

    self.splitter = QtGui.QSplitter(QtCore.Qt.Vertical, self)
    self.splitter.setHandleWidth(1)
    self.splitter.addWidget(self.list)
    self.splitter.addWidget(self.content)
    self.splitter.restoreState(settings.value("splitterSizes").toByteArray());
    self.splitter.splitterMoved.connect(self.splitterMoved)

    self.setCentralWidget(self.splitter)

    def mkAction(name, connect, shortcut=None):
      action = QtGui.QAction(name, self)
      action.triggered.connect(connect)
      if shortcut:
        action.setShortcut(shortcut)
      return action

    mb = self.menuBar()

    fileMenu = mb.addMenu("&File")
    fileMenu.addAction(mkAction("&Close", self.close, "Ctrl+W"))
    fileMenu.addAction(mkAction("&Log Out", self.logOut))
    fileMenu.addSeparator()
    fileMenu.addAction(mkAction("&Exit", self.close, "Ctrl+Q"))

    actionMenu = mb.addMenu("&Action")
    actionMenu.addAction(mkAction("&Reload", self.content.reload, "R"))
    actionMenu.addAction(mkAction("Set &Unread", self.content.setUnread, "U"))
    actionMenu.addAction(mkAction("Toggle &Mark", self.content.toggleMark, "S"))
    actionMenu.addAction(mkAction("Toggle &Publish", self.content.togglePub, "P"))
    actionMenu.addAction(mkAction("&Next", self.content.showNext, "J"))
    actionMenu.addAction(mkAction("&Previous", self.content.showPrevious, "K"))
    actionMenu.addAction(mkAction("&Open in Browser", self.content.openCurrent, "O"))

    viewMenu = mb.addMenu("&View")
    viewMenu.addAction(mkAction("Zoom &In", lambda: self.content.wb.setZoomFactor(self.content.wb.zoomFactor() + 0.2), "Ctrl++"))
    viewMenu.addAction(mkAction("Zoom &Out", lambda: self.content.wb.setZoomFactor(self.content.wb.zoomFactor() - 0.2), "Ctrl+-"))
    viewMenu.addAction(mkAction("&Reset", lambda: self.content.wb.setZoomFactor(1), "Ctrl+0"))
    viewMenu.addAction(mkAction("Scroll", lambda: self.content.wb.page().mainFrame().setScrollPosition(QtCore.QPoint(0, self.content.wb.page().mainFrame().scrollPosition().y() + self.content.wb.page().viewportSize().height() - 30)), "SPACE"))

    helpMenu = mb.addMenu("&Help")
    helpMenu.addAction(mkAction("&About", lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl("http://jabs.nu/feedthemonkey", QtCore.QUrl.TolerantMode)) ))

  def initApp(self):
    session_id = self.get("session_id")
    server_url = self.get("server_url")
    self.tinyTinyRSS = TinyTinyRSS(self, server_url, session_id)

    self.content.evaluateJavaScript("setArticle('loading')")
    self.content.reload()
    self.show()

  def closeEvent(self, ev):
    settings.setValue("geometry", self.saveGeometry())
    settings.setValue("state", self.saveState())
    # with open('feedthemonkey.db', 'w') as outfile:
      # json.dump(self.content.unread_articles, outfile)
    # outfile.close()
    return QtGui.QMainWindow.closeEvent(self, ev)

  def put(self, key, value):
    "Persist an object somewhere under a given key"
    settings.setValue(key, json.dumps(value))
    settings.sync()

  def get(self, key, default=None):
    "Get the object stored under 'key' in persistent storage, or the default value"
    v = settings.value(key)
    return json.loads(unicode(v.toString())) if v.isValid() else default

  def setWindowTitle(self, t):
    super(QtGui.QMainWindow, self).setWindowTitle("Feed the Monkey" + t)

  def splitterMoved(self, pos, index):
    settings.setValue("splitterSizes", self.splitter.saveState());

  def authenticate(self):

    dialog = Login()

    def callback():

      server_url = str(dialog.textServerUrl.text())
      user = str(dialog.textName.text())
      password = str(dialog.textPass.text())

      session_id = TinyTinyRSS.login(server_url, user, password)
      if session_id:
        self.put("session_id", session_id)
        self.put("server_url", server_url)
        self.initApp()
      else:
        self.authenticate()

    dialog.accepted.connect(callback)

    dialog.exec_()

  def logOut(self):
    self.hide()
    self.content.evaluateJavaScript("setArticle('logout')")
    self.tinyTinyRSS.logOut()
    self.tinyTinyRSS = None
    self.put("session_id", None)
    #self.put("server_url", None)
    self.authenticate()

class List(QtGui.QTableWidget):
  def __init__(self, container):
    QtGui.QTableWidget.__init__(self)
    self.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
    self.app = container
    self.itemSelectionChanged.connect(self.rowSelected)
    self.setShowGrid(False)

  def initHeader(self):
    mark = QtGui.QTableWidgetItem("")
    mark.setIcon(QtGui.QIcon(QtGui.QPixmap(iconMark)))
    pub = QtGui.QTableWidgetItem("")
    pub.setIcon(QtGui.QIcon(QtGui.QPixmap(iconPub)))

    self.clear()
    self.setColumnCount(5)
    self.setHorizontalHeaderLabels(("Feed", "", "", "Title", "Date", "Author"))
    self.setHorizontalHeaderItem(1, mark)
    self.setHorizontalHeaderItem(2, pub)
    self.horizontalHeader().setResizeMode(0, QtGui.QHeaderView.ResizeToContents)
    self.horizontalHeader().setResizeMode(1, QtGui.QHeaderView.ResizeToContents)
    self.horizontalHeader().setResizeMode(2, QtGui.QHeaderView.ResizeToContents)
    self.horizontalHeader().setResizeMode(3, QtGui.QHeaderView.Stretch)
    self.horizontalHeader().setResizeMode(4, QtGui.QHeaderView.ResizeToContents)
    self.horizontalHeader().setResizeMode(5, QtGui.QHeaderView.ResizeToContents)
    self.verticalHeader().hide()

  def setItems(self, articles):
    self.initHeader()
    self.setRowCount(len(articles))
    row = 0

    for article in articles:
      if "feed_title" in article:
        feed_title = QtGui.QTableWidgetItem(article["feed_title"])
        feed_title.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
        self.setItem(row, 0, feed_title)
      if "marked" in article:
        if article["marked"]:
          articleMarked = QtGui.QTableWidgetItem("")
          articleMarked.setIcon(QtGui.QIcon(QtGui.QPixmap(iconMarkSet)))
          articleMarked.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.AlignCenter)
          self.setItem(row, 1, articleMarked)
        else:
          articleNotMarked = QtGui.QTableWidgetItem("")
          articleNotMarked.setIcon(QtGui.QIcon(QtGui.QPixmap(iconMarkUnset)))
          articleNotMarked.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.AlignCenter)
          self.setItem(row, 1, articleNotMarked)
      if "published" in article:
        if article["published"]:
          articlePublished = QtGui.QTableWidgetItem("")
          articlePublished.setIcon(QtGui.QIcon(QtGui.QPixmap(iconPubSet)))
          articlePublished.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.AlignCenter)
          self.setItem(row, 2, articlePublished)
        else:
          articleNotPublished = QtGui.QTableWidgetItem("")
          articleNotPublished.setIcon(QtGui.QIcon(QtGui.QPixmap(iconPubUnset)))
          articleNotPublished.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.AlignCenter)
          self.setItem(row, 2, articleNotPublished)
      if "title" in article:
        title = QtGui.QTableWidgetItem(article["title"])
        title.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
        self.setItem(row, 3, title)
      if "updated" in article:
        date = QtCore.QDateTime.fromTime_t(article["updated"]).toString(QtCore.Qt.SystemLocaleShortDate)
        d = QtGui.QTableWidgetItem(date)
        d.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
        self.setItem(row, 4, d)
      if "author" in article:
        author = QtGui.QTableWidgetItem(article["author"])
        author.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
        self.setItem(row, 5, author)
      self.resizeRowToContents(row)
      row += 1
    self.selectRow(0)

  def rowSelected(self):
    indexes = self.selectedIndexes()
    if len(indexes) > 0:
      row = indexes[0].row()
      self.app.content.showIndex(row)

  def updateRead(self):
    for row, article in enumerate(self.app.content.unread_articles):
      for x in [0,3,4]:
        item = self.item(row, x)
        font = item.font()
        font.setBold(article["unread"])
        item.setFont(font)
      if article["marked"]:
        articleMarked = QtGui.QTableWidgetItem("")
        articleMarked.setIcon(QtGui.QIcon(QtGui.QPixmap(iconMarkSet)))
        articleMarked.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.AlignCenter)
        self.setItem(row, 1, articleMarked)
      else:
        articleNotMarked = QtGui.QTableWidgetItem("")
        articleNotMarked.setIcon(QtGui.QIcon(QtGui.QPixmap(iconMarkUnset)))
        articleNotMarked.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.AlignCenter)
        self.setItem(row, 1, articleNotMarked)
      if article["published"]:
        articlePublished = QtGui.QTableWidgetItem("")
        articlePublished.setIcon(QtGui.QIcon(QtGui.QPixmap(iconPubSet)))
        articlePublished.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.AlignCenter)
        self.setItem(row, 2, articlePublished)
      else:
        articleNotPublished = QtGui.QTableWidgetItem("")
        articleNotPublished.setIcon(QtGui.QIcon(QtGui.QPixmap(iconPubUnset)))
        articleNotPublished.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.AlignCenter)
        self.setItem(row, 2, articleNotPublished)

class Content(QtGui.QWidget):
  def __init__(self, container):
    QtGui.QWidget.__init__(self)

    self.app = container
    self.index = 0

    self.wb = QtWebKit.QWebView(titleChanged=lambda t: container.setWindowTitle(t))
    self.wb.page().setLinkDelegationPolicy(QtWebKit.QWebPage.DelegateAllLinks)
    self.wb.linkClicked.connect(lambda url: self.openLink(url))

    self.setLayout(QtGui.QVBoxLayout(spacing=0))
    self.layout().setContentsMargins(0, 0, 0, 0)
    self.layout().addWidget(self.wb)

    self.do_show_next = QtGui.QShortcut(QtCore.Qt.Key_Right, self, activated=self.showNext)
    self.do_show_previous = QtGui.QShortcut(QtCore.Qt.Key_Left, self, activated=self.showPrevious)
    self.do_open = QtGui.QShortcut("Return", self, activated=self.openCurrent)

    self.wb.settings().setAttribute(QtWebKit.QWebSettings.PluginsEnabled, True)
    self.wb.settings().setIconDatabasePath(tempfile.mkdtemp())
    self.wb.setHtml(self.templateString())
    
    self.unread_articles = []

  def openLink(self, url):
    QtGui.QDesktopServices.openUrl(url)

  def reload(self):
    w = WorkerThread(self.app, self._reload)
    self.connect(w, QtCore.SIGNAL("reload_done()"), self.reload_done)
    w.start()

  def setUnread(self):
    article = self.unread_articles[self.index]
    article["unread"] = True
    article["set_unread"] = True
    self.app.tinyTinyRSS.setArticleUnread(article["id"])
    self.app.list.updateRead()

  def toggleMark(self):
    article = self.unread_articles[self.index]
    if article["marked"]:
      article["marked"] = False
    else:
      article["marked"] = True
    self.app.tinyTinyRSS.toggleArticleMark(article["id"])
    self.app.list.updateRead()

  def togglePub(self):
    article = self.unread_articles[self.index]
    if article["published"]:
      article["published"] = False
    else:
      article["published"] = True
    self.app.tinyTinyRSS.toggleArticlePub(article["id"])
    self.app.list.updateRead()

  def _reload(self):
    self.unread_articles = self.app.tinyTinyRSS.getUnreadFeeds()
    self.index = -1

  def load(self):
    # infile = open("feedthemonkey.db")
    # self.unread_articles = json.(infile)
    # infile.close()
    # if len(self.unread_articles) < 1:
    self.reload()
    # else:
    # self.index = -1
    # self.showNext()
    # self.app.list.setItems(self.unread_articles)
    
  def reload_done(self):
    self.setUnreadCount()
    if len(self.unread_articles) > 0:
      self.showNext()
    self.app.list.setItems(self.unread_articles)

  def showIndex(self, index):
    previous = self.unread_articles[self.index]
    if not "set_unread" in previous or not previous["set_unread"]:
      self.app.tinyTinyRSS.setArticleRead(previous["id"])
      previous["unread"] = False
      self.app.list.updateRead()
    else:
      previous["set_unread"] = False
    self.index = index
    current = self.unread_articles[self.index]
    self.setArticle(current)
    self.setUnreadCount()

  def showNext(self):
    if self.index >= 0 and self.index < len(self.unread_articles):
      previous = self.unread_articles[self.index]
      if not "set_unread" in previous or not previous["set_unread"]:
        self.app.tinyTinyRSS.setArticleRead(previous["id"])
        previous["unread"] = False
        self.app.list.updateRead()
      else:
        previous["set_unread"] = False

    if len(self.unread_articles) > self.index + 1:
      self.index += 1
      current = self.unread_articles[self.index]
      self.setArticle(current)
    else:
      if self.index < len(self.unread_articles):
        self.index += 1

    self.setUnreadCount()
    self.app.list.selectRow(self.index)

  def showPrevious(self):
    if self.index > 0:
      self.index -= 1
      previous = self.unread_articles[self.index]
      self.setArticle(previous)
      self.setUnreadCount()
      self.app.list.selectRow(self.index)

  def openCurrent(self):
    current = self.unread_articles[self.index]
    url = QtCore.QUrl(current["link"])
    self.openLink(url)

  def setArticle(self, article):
    func = u"setArticle({});".format(json.dumps(article))
    self.evaluateJavaScript(func)

  def evaluateJavaScript(self, func):
    return self.wb.page().mainFrame().evaluateJavaScript(func)

  def setUnreadCount(self):
    length = len(self.unread_articles)
    i = 0
    if self.index > 0:
      i = self.index
    unread = length - i

    self.app.setWindowTitle(" (" + str(unread) + "/" + str(length) + ")")
    if unread < 1:
      self.evaluateJavaScript("setArticle('empty')")

  def templateString(self):
    html="""
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="utf-8">
        <title>ttrssl</title>
        <script type="text/javascript">
          function $(id) {
            return document.getElementById(id);
          }

          function setArticle(article) {
            window.scrollTo(0, 0);

            $("date").innerHTML = "";
            $("title").innerHTML = "";
            $("title").href = "";
            $("title").title = "";
            $("feed_title").innerHTML = "";
            $("author").innerHTML = "";
            $("article").innerHTML = "";

            if(article == "empty") {

              $("article").innerHTML = "No unread articles to display.";

            } else if(article == "loading") {

              $("article").innerHTML = "Loading <blink>&hellip;</blink>";

            } else if (article == "logout") {

            } else if(article) {

              $("date").innerHTML = (new Date(parseInt(article.updated, 10) * 1000));
              $("title").innerHTML = article.title;
              $("title").href = article.link;
              $("title").title = article.link;
              $("feed_title").innerHTML = article.feed_title;
              $("author").innerHTML = "";
              if(article.author && article.author.length > 0)
                $("author").innerHTML = "&ndash; " + article.author
              $("article").innerHTML = article.content;
            }
          }
        </script>
        <style type="text/css">
          body {
            font-family: "Ubuntu", "Lucida Grande", "Tahoma", sans-serif;
            padding: 1em 2em 1em 2em;
          }
          body.darwin {
            font-family: "LucidaGrande", sans-serif;
          }
          h1 {
            font-weight: normal;
            margin: 0;
            padding: 0;
          }
          header {
            margin-bottom: 1em;
            border-bottom: 1px solid #aaa;
            padding-bottom: 1em;
          }
          header p {
            color: #aaa;
            margin: 0;
            padding: 0
          }
          a {
            color: #772953;
            text-decoration: none;
          }
          img {
            max-width: 100%;
            height: auto;
          }
          article {
            line-height: 1.6;
          }
        </style>
      </head>
      <body class='""" + _platform + """''>
        <header>
          <p><span id="feed_title"></span> <span id="author"></span></p>
          <h1><a id="title" href=""></a></h1>
          <p><timedate id="date"></timedate></p>
        </header>
        <article id="article"></article>
      </body>
      </html>"""
    return html # string.replace(html, "<body", "<body class='" + _platform + "'")

class TinyTinyRSS:
  def __init__(self, app, server_url, session_id):
    self.app = app
    if server_url and session_id:
      self.server_url = server_url
      self.session_id = session_id
    else:
      self.app.authenticate()

  def doOperation(self, operation, options=None):
    url = self.server_url + "/api/"
    default_options = {'sid': self.session_id, 'op': operation}
    if options:
      options = dict(default_options.items() + options.items())
    else:
      options = default_options
    json_string = json.dumps(options)
    req = urllib2.Request(url)
    fd = urllib2.urlopen(req, json_string)
    body = ""
    while True:
      data = fd.read(1024)
      if not len(data):
        break
      body += data

    return json.loads(body)["content"]

  def getUnreadFeeds(self):
    unread_articles = []
    def more(skip):
      return self.doOperation("getHeadlines", {"show_excerpt": False, "view_mode": "unread", "show_content": True, "feed_id": -4, "skip": skip})

    skip = 0
    while True:
      new = more( skip)
      unread_articles += new
      length = len(new)

      if length < 1:
        break
      skip += length

    return unread_articles

  def setArticleRead(self, article_id):
    l = lambda: self.doOperation("updateArticle", {'article_ids':article_id, 'mode': 0, 'field': 2})
    t = Thread(target=l)
    t.start()

  def setArticleUnread(self, article_id):
    l = lambda: self.doOperation("updateArticle", {'article_ids':article_id, 'mode': 1, 'field': 2})
    t = Thread(target=l)
    t.start()

  def toggleArticleMark(self, article_id):
    l = lambda: self.doOperation("updateArticle", {'article_ids':article_id, 'mode': 2, 'field': 0})
    t = Thread(target=l)
    t.start()

  def toggleArticlePub(self, article_id):
    l = lambda: self.doOperation("updateArticle", {'article_ids':article_id, 'mode': 2, 'field': 1})
    t = Thread(target=l)
    t.start()

  def logOut(self):
    self.doOperation("logout")

  @classmethod
  def login(self, server_url, user, password):
    url = server_url + "/api/"
    options = {"op": "login", "user": user, "password": password}
    json_string = json.dumps(options)
    req = urllib2.Request(url)
    fd = urllib2.urlopen(req, json_string)
    body = ""
    while 1:
      data = fd.read(1024)
      if not len(data):
        break
      body += data

    body = json.loads(body)["content"]

    if body.has_key("error"):
      msgBox = QtGui.QMessageBox()
      msgBox.setText(body["error"])
      msgBox.exec_()
      return None

    return body["session_id"]

class Login(QtGui.QDialog):
  def __init__(self):
    QtGui.QDialog.__init__(self)
    self.setWindowIcon(QtGui.QIcon(iconApp))
    self.setWindowTitle("Feed the Monkey - Login")

    self.label = QtGui.QLabel(self)
    self.label.setText("Please specify a server url, a username and a password.")

    self.textServerUrl = QtGui.QLineEdit(self)
    self.textServerUrl.setPlaceholderText("http://example.com/ttrss/")
    if self.get("server_url"):
      self.textServerUrl.setText(self.get("server_url"))

    self.textName = QtGui.QLineEdit(self)
    self.textName.setPlaceholderText("username")

    self.textPass = QtGui.QLineEdit(self)
    self.textPass.setEchoMode(QtGui.QLineEdit.Password);
    self.textPass.setPlaceholderText("password")

    self.buttons = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok)
    self.buttons.accepted.connect(self.accept)

    layout = QtGui.QVBoxLayout(self)
    layout.addWidget(self.label)
    layout.addWidget(self.textServerUrl)
    layout.addWidget(self.textName)
    layout.addWidget(self.textPass)
    layout.addWidget(self.buttons)
    
  def get(self, key, default=None):
    "Get the object stored under 'key' in persistent storage, or the default value"
    v = settings.value(key)
    return json.loads(unicode(v.toString())) if v.isValid() else default

class WorkerThread(QtCore.QThread):

  def __init__(self, parent, do_reload):
    super(WorkerThread, self).__init__(parent)
    self.do_reload = do_reload

  def run(self):
    self.do_reload()
    self.emit(QtCore.SIGNAL("reload_done()"))

if __name__ == "__main__":
  app = QtGui.QApplication(sys.argv)
  wb = MainWindow()
  wb.show()
  sys.exit(app.exec_())
