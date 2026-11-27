using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Reflection;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

[assembly: AssemblyTitle("Talep Kontrol Kurulum")]
[assembly: AssemblyVersion("6.2.1.0")]

internal static class Art
{
	public static GraphicsPath Round(RectangleF r, float radius)
	{
		float n = radius * 2f;
		var p = new GraphicsPath();
		p.AddArc(r.X, r.Y, n, n, 180f, 90f);
		p.AddArc(r.Right - n, r.Y, n, n, 270f, 90f);
		p.AddArc(r.Right - n, r.Bottom - n, n, n, 0f, 90f);
		p.AddArc(r.X, r.Bottom - n, n, n, 90f, 90f);
		p.CloseFigure();
		return p;
	}

	public static void Fill(Graphics g, RectangleF r, float radius, Color c)
	{
		using var path = Round(r, radius);
		using var brush = new SolidBrush(c);
		g.FillPath(brush, path);
	}

	public static void Text(Graphics g, string text, Font font, Color color, Rectangle r, ContentAlignment align)
	{
		var flags = TextFormatFlags.EndEllipsis | TextFormatFlags.NoPadding | TextFormatFlags.NoPrefix;
		flags |= align == ContentAlignment.MiddleCenter ? TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter
			: TextFormatFlags.Left | TextFormatFlags.VerticalCenter;
		TextRenderer.DrawText(g, text, font, r, color, flags);
	}
}

internal sealed class SoftButton : Button
{
	bool hover, down;
	public bool Primary;

	public SoftButton()
	{
		SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw | ControlStyles.SupportsTransparentBackColor, true);
		BackColor = Color.FromArgb(4, 14, 28);
		FlatStyle = FlatStyle.Flat;
		FlatAppearance.BorderSize = 0;
		Cursor = Cursors.Hand;
	}

	protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
	protected override void OnMouseLeave(EventArgs e) { hover = down = false; Invalidate(); base.OnMouseLeave(e); }
	protected override void OnMouseDown(MouseEventArgs e) { down = true; Invalidate(); base.OnMouseDown(e); }
	protected override void OnMouseUp(MouseEventArgs e) { down = false; Invalidate(); base.OnMouseUp(e); }
	protected override void OnEnabledChanged(EventArgs e) { Invalidate(); base.OnEnabledChanged(e); }
	protected override void OnPaintBackground(PaintEventArgs e) { e.Graphics.Clear(BackColor); }

	protected override void OnPaint(PaintEventArgs e)
	{
		var g = e.Graphics;
		var parent = Parent;
		if (parent == null) g.Clear(BackColor);
		else
		{
			using var bg = new LinearGradientBrush(new Rectangle(-Left, -Top, parent.ClientSize.Width, parent.ClientSize.Height),
				Color.FromArgb(5, 17, 34), Color.FromArgb(3, 12, 24), 90f);
			g.FillRectangle(bg, ClientRectangle);
		}
		g.SmoothingMode = SmoothingMode.AntiAlias;
		var r = new RectangleF(3f, 2f, Width - 6, Height - 9);
		float rad = Primary ? 23 : 10;
		if (Primary)
		{
			Color c1 = !Enabled ? Color.FromArgb(15, 34, 53) : hover ? Color.FromArgb(30, 97, 134) : Color.FromArgb(25, 77, 111);
			Color c2 = Enabled ? Color.FromArgb(13, 44, 70) : Color.FromArgb(10, 26, 44);
			if (down) { c1 = Color.FromArgb(14, 45, 68); c2 = Color.FromArgb(21, 64, 89); }
			using var path = Art.Round(r, rad);
			using var brush = new LinearGradientBrush(r, c1, c2, 90f);
			g.FillPath(brush, path);
			using var pen = new Pen(Color.FromArgb(Enabled ? 95 : 35, 111, 196, 226));
			g.DrawPath(pen, path);
		}
		else
		{
			Art.Fill(g, new RectangleF(r.X, r.Y + 2f, r.Width, r.Height - 2f), rad, Color.FromArgb(2, 9, 19));
			Art.Fill(g, r, rad, (hover || Focused) ? Color.FromArgb(26, 52, 75) : Color.FromArgb(17, 37, 58));
			using var path = Art.Round(r, rad);
			using var pen = new Pen(Color.FromArgb(43, 85, 130, 161));
			g.DrawPath(pen, path);
		}
		Art.Text(g, Text, Font,
			!Enabled ? Color.FromArgb(100, 130, 151) : Primary ? Color.FromArgb(228, 242, 250) : Color.FromArgb(141, 175, 196),
			Rectangle.Round(r), ContentAlignment.MiddleCenter);
	}
}

[DataContract]
internal sealed class ActivePublication
{
	[DataMember(Name = "schema")] public int Schema;
	[DataMember(Name = "product")] public string Product;
	[DataMember(Name = "release_id")] public string ReleaseId;
	[DataMember(Name = "package")] public string Package;
	[DataMember(Name = "sha256")] public string Sha256;
	[DataMember(Name = "size_bytes")] public long SizeBytes;
	public string PackagePath;
}

[DataContract]
internal sealed class InstalledConfiguration
{
	[DataMember(Name = "auto_install_updates")] public bool AutoInstallUpdates;
	[DataMember(Name = "update_share")] public string UpdateShare;
	[DataMember(Name = "product_name")] public string ProductName;
	[DataMember(Name = "external_root")] public string ExternalRoot;
	[DataMember(Name = "shared_writes_enabled")] public bool SharedWritesEnabled;
}

internal enum InstallChoice { Cancel, Update, Clean }

internal sealed class Setup : Form
{
	readonly CancellationTokenSource stop = new CancellationTokenSource();
	ActivePublication selectedPublication;
	bool deploymentRunning, busy, installing;
	readonly TextBox source = new TextBox();
	readonly TextBox target = new TextBox();
	readonly TextBox log = new TextBox();
	readonly ListBox packages = new ListBox();
	SoftButton scan, install, details;
	readonly ProgressBar progress = new ProgressBar();
	readonly Label status = new Label();
	string phaseText = "Kaynak klasörü kontrol ediliyor…";
	double phase;
	readonly System.Windows.Forms.Timer animation = new System.Windows.Forms.Timer();
	Image logo;
	Icon brand;
	int transferCount;
	string currentTransferredName = "";
	readonly Color muted = Color.FromArgb(134, 164, 187);
	readonly Font titleFont = new Font("Segoe UI", 27f, FontStyle.Bold);
	readonly Font bodyFont = new Font("Segoe UI", 11f);
	readonly Font smallFont = new Font("Segoe UI", 9f);
	readonly Font microFont = new Font("Segoe UI", 8.5f);

	static string LocalAppData => Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
	static string DefaultInstallDir => Path.Combine(LocalAppData, "Programs", "TalepKontrol");
	static string UserDataRoot => Path.Combine(LocalAppData, "TalepKontrol");

	[STAThread]
	static void Main(string[] args)
	{
		Application.EnableVisualStyles();
		Application.SetCompatibleTextRenderingDefault(false);
		if (args.Length == 2 && args[0] == "--validate")
		{
			Validate(args[1]);
			return;
		}
		if (args.Length >= 1 && (args[0] == "--clean-install" || args[0] == "/clean"))
		{
			Application.Run(new Setup(forceCleanPrompt: true));
			return;
		}
		Application.Run(new Setup());
	}

	readonly bool forceCleanPrompt;

	public Setup(bool forceCleanPrompt = false)
	{
		this.forceCleanPrompt = forceCleanPrompt;
		Text = "Talep Kontrol Kurulum";
		ClientSize = new Size(500, 710);
		FormBorderStyle = FormBorderStyle.FixedSingle;
		MaximizeBox = false;
		StartPosition = FormStartPosition.CenterScreen;
		BackColor = Color.FromArgb(5, 17, 34);
		DoubleBuffered = true;
		Font = bodyFont;

		try
		{
			using var ico = Assembly.GetExecutingAssembly().GetManifestResourceStream("TalepKontrol.ico");
			if (ico != null)
			{
				brand = new Icon(ico);
				Icon = brand;
			}
			using var png = Assembly.GetExecutingAssembly().GetManifestResourceStream("TalepKontrol_Logo.png");
			if (png != null) logo = Image.FromStream(png);
		}
		catch { /* marka görselleri yoksa sade arayüz */ }

		source.Visible = target.Visible = packages.Visible = log.Visible = status.Visible = progress.Visible = false;
		source.Text = GuessShareRoot();
		target.Text = DefaultInstallDir;

		scan = MakeButton("Yeniden tara", 28, 520, 130, 40, false, async (_, __) => await Scan());
		details = MakeButton("Ayarlar", 170, 520, 110, 40, false, (_, __) => Settings());
		install = MakeButton("Kurulumu Başlat", 292, 520, 180, 40, true, async (_, __) => await Install());

		animation.Interval = 33;
		animation.Tick += (_, __) => { phase += 0.09; Invalidate(); };
		animation.Start();
		FormClosing += OnCloseRequested;
		Shown += async (_, __) => await Scan();
	}

	SoftButton MakeButton(string text, int x, int y, int w, int h, bool primary, EventHandler action)
	{
		var b = new SoftButton { Text = text, Bounds = new Rectangle(x, y, w, h), Primary = primary, Font = smallFont };
		b.Click += action;
		Controls.Add(b);
		return b;
	}

	protected override void Dispose(bool disposing)
	{
		if (disposing)
		{
			animation.Stop();
			animation.Dispose();
			logo?.Dispose();
			brand?.Dispose();
			titleFont.Dispose();
			bodyFont.Dispose();
			smallFont.Dispose();
			microFont.Dispose();
		}
		base.Dispose(disposing);
	}

	void OnCloseRequested(object sender, FormClosingEventArgs e)
	{
		stop.Cancel();
		if (deploymentRunning)
		{
			e.Cancel = true;
			Hide();
			animation.Stop();
		}
	}

	static string GuessShareRoot()
	{
		var unc = @"\\cedas.com\paylasim\GM_Planlama_Tesis_Direktorlugu\MALZEME YÖNETİMİ MÜDÜRLÜĞÜ\3 - Müdürlük Ortak Alan\1-Ortak Döküman Alanı\8-Talep Kontrol\9-Uygulama";
		try
		{
			var cfg = Path.Combine(DefaultInstallDir, "config.json");
			if (File.Exists(cfg))
			{
				using var fs = File.OpenRead(cfg);
				var conf = (InstalledConfiguration)new DataContractJsonSerializer(typeof(InstalledConfiguration)).ReadObject(fs);
				var share = conf?.UpdateShare ?? "";
				if (share.EndsWith(@"\Aktif", StringComparison.OrdinalIgnoreCase))
					return Path.GetFullPath(Path.Combine(share, ".."));
			}
		}
		catch { }
		return unc;
	}

	protected override void OnPaint(PaintEventArgs e)
	{
		base.OnPaint(e);
		var g = e.Graphics;
		g.SmoothingMode = SmoothingMode.AntiAlias;
		float sx = ClientSize.Width / 500f, sy = ClientSize.Height / 710f;
		g.ScaleTransform(sx, sy);
		using (var bg = new LinearGradientBrush(new Rectangle(0, 0, 500, 710), Color.FromArgb(5, 17, 34), Color.FromArgb(3, 12, 24), 90f))
			g.FillRectangle(bg, 0, 0, 500, 710);
		Art.Text(g, "Talep Kontrol", titleFont, Color.FromArgb(238, 245, 252), new Rectangle(20, 216, 460, 54), ContentAlignment.MiddleCenter);
		using (var f = new Font("Segoe UI", 12f))
			Art.Text(g, "K U R U L U M", f, Color.FromArgb(153, 182, 202), new Rectangle(20, 267, 460, 30), ContentAlignment.MiddleCenter);
		if (logo != null)
		{
			var bounce = (float)Math.Sin(phase * 0.45) * 1.5f;
			g.DrawImage(logo, new RectangleF(204f, 98f + bounce, 92f, 92f));
		}
		Art.Text(g, phaseText, bodyFont, muted, new Rectangle(28, 311, 444, 32), ContentAlignment.MiddleCenter);
		var hint = !busy
			? (packages.SelectedItem == null ? "Paket klasörünü Ayarlar’dan seçebilirsiniz." : Path.GetFileName(packages.SelectedItem.ToString()))
			: (installing ? "Dosyalar hazırlanıyor, lütfen bekleyin." : "Kurulum paketleri kontrol ediliyor.");
		Art.Text(g, hint, smallFont, muted, new Rectangle(30, 576, 440, 20), ContentAlignment.MiddleCenter);
		Art.Text(g, transferCount > 0 ? ("AKTARILAN DOSYALAR · " + transferCount) : "AKTARILAN DOSYALAR",
			microFont, Color.FromArgb(110, 148, 175), new Rectangle(68, 644, 395, 18), ContentAlignment.MiddleLeft);
		var line = currentTransferredName.Length != 0 ? currentTransferredName
			: (busy ? "Paket dosyaları hazırlanıyor…" : "Kurulum başlayınca dosya adları burada görünür.");
		Art.Text(g, line, smallFont, Color.FromArgb(191, 212, 227), new Rectangle(68, 664, 395, 23), ContentAlignment.MiddleLeft);
	}

	void Busy(bool value)
	{
		busy = value;
		scan.Enabled = details.Enabled = !value;
		install.Enabled = !value && packages.Items.Count > 0;
		install.Text = !value
			? (packages.Items.Count > 0 ? "Kurulumu Başlat" : "Paket bulunamadı")
			: (installing ? "Kurulum sürüyor…" : "Paket aranıyor…");
		if (value) phaseText = installing ? "Kurulumunuz hazırlanıyor" : "Paket klasörleri kontrol ediliyor";
		Invalidate();
	}

	void Log(string text)
	{
		if (stop.IsCancellationRequested) return;
		if (InvokeRequired) { Invoke(new Action<string>(Log), text); return; }
		log.AppendText(DateTime.Now.ToString("HH:mm:ss") + "  " + text + Environment.NewLine);
		status.Text = text;
		Invalidate();
	}

	async Task Scan()
	{
		Busy(true);
		packages.Items.Clear();
		selectedPublication = null;
		try
		{
			var root = source.Text.Trim();
			var pub = await Task.Run(() =>
			{
				var p = ReadActivePublication(root);
				VerifyApprovedPackage(p);
				Validate(p.PackagePath);
				return p;
			});
			if (!stop.IsCancellationRequested)
			{
				selectedPublication = pub;
				packages.Items.Add(pub.PackagePath);
				packages.SelectedIndex = 0;
				phaseText = "Onaylı yayın doğrulandı";
				Log("Aktif yayın doğrulandı. Kimlik: " + pub.ReleaseId);
			}
		}
		catch (Exception ex)
		{
			phaseText = "Onaylı yayın bulunamadı";
			Log("Kurulum durduruldu: " + ex.Message);
		}
		finally { Busy(false); }
	}

	Form Dialog(string title, int w, int h) => new Form
	{
		Text = "Talep Kontrol | " + title,
		ClientSize = new Size(w, h),
		StartPosition = FormStartPosition.CenterParent,
		BackColor = Color.FromArgb(7, 20, 36),
		ForeColor = Color.FromArgb(209, 228, 242),
		Font = bodyFont,
		FormBorderStyle = FormBorderStyle.FixedDialog,
		MaximizeBox = false,
		MinimizeBox = false,
		Padding = new Padding(20),
		Icon = Icon
	};

	void Settings()
	{
		using var f = Dialog("Kaynak ve paketler", 740, 360);
		f.Controls.Add(new Label { Text = "Kurulum paketlerinin bulunduğu kaynak klasörü", Bounds = new Rectangle(22, 20, 690, 25) });
		var src = new TextBox { Text = source.Text, Bounds = new Rectangle(22, 53, 565, 28) };
		f.Controls.Add(src);
		var browse = new Button { Text = "Klasör seç", Bounds = new Rectangle(600, 51, 117, 33) };
		browse.Click += (_, __) =>
		{
			using var d = new FolderBrowserDialog { SelectedPath = src.Text, Description = "Kurulum ZIP paketlerinin bulunduğu klasörü seçin" };
			if (d.ShowDialog(f) == DialogResult.OK) src.Text = d.SelectedPath;
		};
		f.Controls.Add(browse);
		f.Controls.Add(new Label { Text = "Uygulamanın kurulacağı klasör (sabit)", Bounds = new Rectangle(22, 110, 690, 25) });
		f.Controls.Add(new TextBox { Text = target.Text, Bounds = new Rectangle(22, 140, 695, 28), ReadOnly = true });
		var ok = new Button { Text = "Uygula", Bounds = new Rectangle(580, 280, 137, 38), DialogResult = DialogResult.OK };
		var cancel = new Button { Text = "Vazgeç", Bounds = new Rectangle(434, 280, 130, 38), DialogResult = DialogResult.Cancel };
		f.Controls.Add(ok); f.Controls.Add(cancel);
		f.AcceptButton = ok; f.CancelButton = cancel;
		if (f.ShowDialog(this) == DialogResult.OK)
		{
			var changed = source.Text != src.Text.Trim();
			source.Text = src.Text.Trim();
			if (changed) _ = Scan();
		}
	}

	InstallChoice ChooseExistingInstall(string dest, bool hasUserData)
	{
		using var f = Dialog("Mevcut Talep Kontrol kurulumu", 600, 300);
		var msg =
			"Mevcut kurulum veya eski yerel veri bulundu.\n" + dest + "\n\n" +
			"Güncelle: Yerel kullanıcı verileri yeni kuruluma taşınır.\n" +
			"Temiz kurulum: Çalışan süreçler durdurulur; kurulum klasörü,\n" +
			"%LOCALAPPDATA%\\TalepKontrol (Index, WebView2, güncelleme kayıtları)\n" +
			"ve eski yedek/geçici klasörler tamamen silinir; sıfırdan kurulur.";
		f.Controls.Add(new Label { Text = msg, Bounds = new Rectangle(22, 16, 550, 180), ForeColor = Color.FromArgb(209, 228, 242) });
		var update = new Button { Text = "Güncelle", Bounds = new Rectangle(22, 210, 115, 38), DialogResult = DialogResult.Yes, Enabled = Directory.Exists(dest) };
		var clean = new Button { Text = "Temiz kurulum", Bounds = new Rectangle(150, 210, 155, 38), DialogResult = DialogResult.Retry };
		var cancel = new Button { Text = "İptal", Bounds = new Rectangle(320, 210, 105, 38), DialogResult = DialogResult.Cancel };
		f.Controls.AddRange(new Control[] { update, clean, cancel });
		f.CancelButton = cancel;
		f.ActiveControl = clean;
		var r = f.ShowDialog(this);
		if (r == DialogResult.Yes) return InstallChoice.Update;
		if (r == DialogResult.Retry) return InstallChoice.Clean;
		return InstallChoice.Cancel;
	}

	bool ConfirmCleanInstall()
	{
		return MessageBox.Show(this,
			"Temiz kurulum eski Talep Kontrol kurulumunu ve bu kullanıcıdaki tüm yerel verileri kalıcı olarak siler.\n\n" +
			"Silinecekler:\n" +
			"• " + DefaultInstallDir + "\n" +
			"• " + UserDataRoot + "\n" +
			"• Masaüstü kısayolu yenilenir\n\n" +
			"0-Database merkezi kayıtları etkilenmez.\n\nDevam edilsin mi?",
			"Temiz kurulum onayı",
			MessageBoxButtons.YesNo,
			MessageBoxIcon.Warning,
			MessageBoxDefaultButton.Button2) == DialogResult.Yes;
	}

	DialogResult CompleteDialog()
	{
		using var f = Dialog("Kurulum tamamlandı", 440, 180);
		f.Controls.Add(new Label
		{
			Text = "Talep Kontrol kurulumu tamamlandı.\nUygulamayı şimdi başlatmak ister misiniz?",
			Bounds = new Rectangle(22, 24, 396, 60),
			TextAlign = ContentAlignment.MiddleCenter,
			ForeColor = Color.FromArgb(209, 228, 242)
		});
		var open = new Button { Text = "Uygulamayı Aç", Bounds = new Rectangle(42, 112, 170, 40), DialogResult = DialogResult.Yes };
		var close = new Button { Text = "Kapat", Bounds = new Rectangle(226, 112, 170, 40), DialogResult = DialogResult.No };
		f.Controls.Add(open); f.Controls.Add(close);
		return f.ShowDialog(this);
	}

	async Task Install()
	{
		if (packages.SelectedItem == null || selectedPublication == null) return;
		var dest = Path.GetFullPath(target.Text.Trim()).TrimEnd('\\');
		var expected = Path.GetFullPath(DefaultInstallDir).TrimEnd('\\');
		if (!string.Equals(dest, expected, StringComparison.OrdinalIgnoreCase))
		{
			Log("Otomatik güncelleme için hedef klasör: " + expected);
			return;
		}
		if (dest == Path.GetPathRoot(dest)?.TrimEnd('\\') || dest.Length < 6)
		{
			Log("Lütfen uygulamaya özel bir hedef klasör seçin.");
			return;
		}
		try
		{
			var latest = ReadActivePublication(source.Text.Trim());
			if (latest.Sha256 != selectedPublication.Sha256 || latest.PackagePath != packages.SelectedItem.ToString())
				throw new InvalidDataException("Aktif yayın değişmiş. Önce Yeniden tara seçeneğine basın.");

			bool replacing = Directory.Exists(dest);
			bool hasUserData = Directory.Exists(UserDataRoot);
			bool cleanInstall = forceCleanPrompt;

			if (forceCleanPrompt)
			{
				if (!ConfirmCleanInstall()) { Log("Kurulum kullanıcı tarafından iptal edildi."); return; }
				cleanInstall = true;
			}
			else if (replacing || hasUserData)
			{
				var choice = ChooseExistingInstall(dest, hasUserData);
				if (choice == InstallChoice.Cancel) { Log("Kurulum kullanıcı tarafından iptal edildi."); return; }
				cleanInstall = choice == InstallChoice.Clean;
				if (cleanInstall && !ConfirmCleanInstall()) { Log("Kurulum kullanıcı tarafından iptal edildi."); return; }
			}
			else
			{
				if (MessageBox.Show(this, "Talep Kontrol şu klasöre kurulacak:\n" + dest + "\n\nKuruluma başlansın mı?",
					"Talep Kontrol kurulumu", MessageBoxButtons.YesNo, MessageBoxIcon.Question, MessageBoxDefaultButton.Button2) != DialogResult.Yes)
				{
					Log("Kurulum kullanıcı tarafından iptal edildi.");
					return;
				}
			}

			installing = true;
			transferCount = 0;
			currentTransferredName = "";
			Invalidate();
			Busy(true);
			deploymentRunning = true;
			bool doClean = cleanInstall;
			await Task.Run(() => Deploy(latest, dest, replacing, doClean));
			deploymentRunning = false;
			if (!stop.IsCancellationRequested)
			{
				phaseText = "Kurulum başarıyla tamamlandı";
				Log("Onaylı kurulum tamamlandı.");
				progress.Value = 100;
				if (CompleteDialog() == DialogResult.Yes) LaunchInstalled(dest);
				Close();
			}
		}
		catch (OperationCanceledException) { }
		catch (Exception ex)
		{
			phaseText = "Kurulum tamamlanamadı • Günlüğü kontrol edin";
			Log("Kurulum durduruldu: " + ex.Message);
		}
		finally
		{
			deploymentRunning = false;
			installing = false;
			if (stop.IsCancellationRequested) { if (!IsDisposed) Close(); }
			else Busy(false);
		}
	}

	void LaunchInstalled(string dest)
	{
		var launcher = Path.Combine(dest, "Talep Kontrol.vbs");
		if (!File.Exists(launcher))
		{
			MessageBox.Show(this, "Otomatik güncelleme başlatıcısı bulunamadı.", Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
			return;
		}
		Process.Start(new ProcessStartInfo
		{
			FileName = "wscript.exe",
			Arguments = "\"" + launcher + "\"",
			WorkingDirectory = dest,
			UseShellExecute = false
		});
	}

	static bool PathLooksLikeTalep(string path)
	{
		if (string.IsNullOrWhiteSpace(path)) return false;
		var p = path.Replace('/', '\\');
		return p.IndexOf("\\TalepKontrol", StringComparison.OrdinalIgnoreCase) >= 0
			|| p.IndexOf("\\Talep Kontrol", StringComparison.OrdinalIgnoreCase) >= 0
			|| p.IndexOf("windows_launcher.py", StringComparison.OrdinalIgnoreCase) >= 0
			|| p.IndexOf("START_GUI.ps1", StringComparison.OrdinalIgnoreCase) >= 0
			|| p.IndexOf("\\TalepKontrol\\WebView2UserData", StringComparison.OrdinalIgnoreCase) >= 0;
	}

	static void TryKillProcess(Process process, Action<string> log, string reason)
	{
		try
		{
			if (process == null || process.HasExited) return;
			if (process.Id == Process.GetCurrentProcess().Id) return;
			log("Kilitli süreç kapatılıyor: " + process.ProcessName + " (" + process.Id + ") · " + reason);
			try { process.CloseMainWindow(); } catch { }
			if (!process.WaitForExit(800))
			{
				process.Kill();
				process.WaitForExit(2000);
			}
		}
		catch (Exception ex)
		{
			try { log("Süreç kapatılamadı: " + process.ProcessName + " · " + ex.Message); } catch { }
		}
		finally
		{
			try { process.Dispose(); } catch { }
		}
	}

	static void StopRunningServices(Action<string> log, string installDir = null)
	{
		for (int port = 8765; port <= 8769; port++)
		{
			try
			{
				var req = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + port + "/api/health");
				req.Timeout = 400;
				req.Method = "GET";
				using var resp = (HttpWebResponse)req.GetResponse();
				using var reader = new StreamReader(resp.GetResponseStream());
				var body = reader.ReadToEnd();
				if (body.IndexOf("Talep Kontrol", StringComparison.OrdinalIgnoreCase) < 0) continue;
				log("Çalışan servis kapatılıyor: " + port);
				var stopReq = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + port + "/api/shutdown");
				stopReq.Timeout = 1500;
				stopReq.Method = "POST";
				stopReq.ContentLength = 0;
				try { using (stopReq.GetResponse()) { } } catch { }
			}
			catch { }
		}
		Thread.Sleep(700);

		// Window-title filter: START_GUI WebView penceresi "Talep Kontrol"
		try
		{
			var killTitle = new ProcessStartInfo
			{
				FileName = "taskkill",
				Arguments = "/F /FI \"WINDOWTITLE eq Talep Kontrol*\"",
				CreateNoWindow = true,
				UseShellExecute = false,
				RedirectStandardOutput = true,
				RedirectStandardError = true
			};
			using var tp = Process.Start(killTitle);
			tp?.WaitForExit(3000);
		}
		catch { }

		var installFull = string.IsNullOrWhiteSpace(installDir) ? "" : Path.GetFullPath(installDir.TrimEnd('\\'));
		foreach (var name in new[] { "python", "pythonw", "powershell", "pwsh", "msedgewebview2", "wscript", "cscript" })
		{
			Process[] list = null;
			try { list = Process.GetProcessesByName(name); }
			catch { continue; }
			foreach (var p in list)
			{
				try
				{
					string module = null;
					try { module = p.MainModule?.FileName; } catch { }
					string title = null;
					try { title = p.MainWindowTitle; } catch { }
					bool match =
						(!string.IsNullOrEmpty(installFull) && !string.IsNullOrEmpty(module) &&
							module.StartsWith(installFull + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
						|| PathLooksLikeTalep(module)
						|| (!string.IsNullOrEmpty(title) && title.IndexOf("Talep Kontrol", StringComparison.OrdinalIgnoreCase) >= 0);
					// WebView2: yalnızca TalepKontrol kullanıcı veri yolu / başlık eşleşirse
					if (string.Equals(name, "msedgewebview2", StringComparison.OrdinalIgnoreCase) && !match)
					{
						p.Dispose();
						continue;
					}
					if (match) TryKillProcess(p, log, module ?? title ?? name);
					else p.Dispose();
				}
				catch { try { p.Dispose(); } catch { } }
			}
		}
		Thread.Sleep(500);
	}

	static void TryDeleteDirectory(string path, Action<string> log)
	{
		if (string.IsNullOrWhiteSpace(path) || !Directory.Exists(path)) return;
		for (int attempt = 0; attempt < 5; attempt++)
		{
			try
			{
				foreach (var f in Directory.GetFiles(path, "*", SearchOption.AllDirectories))
				{
					try { File.SetAttributes(f, FileAttributes.Normal); } catch { }
				}
				Directory.Delete(path, true);
				log("Silindi: " + path);
				return;
			}
			catch (Exception ex)
			{
				Thread.Sleep(400 * (attempt + 1));
				if (attempt == 4) log("Silinemedi: " + path + " | " + ex.Message);
			}
		}
	}

	void PurgePreviousInstallation(string dest)
	{
		Log("Temiz kurulum: eski süreçler ve yerel veriler temizleniyor…");
		StopRunningServices(Log, dest);

		var programs = Path.Combine(LocalAppData, "Programs");
		TryDeleteDirectory(dest, Log);
		if (Directory.Exists(dest))
		{
			Log("Hedef klasör hâlâ kilitli; süreçler yeniden kapatılıyor…");
			StopRunningServices(Log, dest);
			TryDeleteDirectory(dest, Log);
		}
		if (Directory.Exists(programs))
		{
			foreach (var dir in Directory.GetDirectories(programs))
			{
				var name = Path.GetFileName(dir);
				if (name.StartsWith("TalepKontrol", StringComparison.OrdinalIgnoreCase) ||
					name.StartsWith(".TalepKontrol", StringComparison.OrdinalIgnoreCase))
					TryDeleteDirectory(dir, Log);
			}
			foreach (var file in Directory.GetFiles(programs, ".TalepKontrol-*"))
			{
				try { File.Delete(file); Log("Silindi: " + file); } catch (Exception ex) { Log("Silinemedi: " + file + " | " + ex.Message); }
			}
		}

		TryDeleteDirectory(UserDataRoot, Log);

		var temp = Path.GetTempPath();
		foreach (var pattern in new[] { "YEDAS_TalepKontrol_*", "TalepKontrol-*" })
		{
			try
			{
				foreach (var f in Directory.GetFiles(temp, pattern))
				{
					try { File.Delete(f); } catch { }
				}
			}
			catch { }
		}

		try
		{
			var link = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Talep Kontrol.lnk");
			if (File.Exists(link)) File.Delete(link);
		}
		catch { }

		Log("Eski kurulum ve yerel veri temizliği tamamlandı.");
	}

	void Deploy(ActivePublication publication, string dest, bool replacing, bool cleanInstall)
	{
		string stage = Path.GetFullPath(dest + ".hazirlik-" + Guid.NewGuid().ToString("N"));
		string previous = Path.GetFullPath(dest + ".gecici-" + Guid.NewGuid().ToString("N"));
		string zipCopy = Path.Combine(Path.GetTempPath(), "TalepKontrol-" + Guid.NewGuid().ToString("N") + ".zip");
		bool movedOld = false;
		try
		{
			// ZIP aktarımından önce çalışan uygulamayı kapat — aksi halde 113 dosya
			// aktarılsa bile hedef klasör taşınamaz / temizlenemez.
			StopRunningServices(Log, dest);

			if (cleanInstall)
			{
				// ZIP kopyası %TEMP% altında; kullanıcı veri kökü güvenle silinebilir.
				PurgePreviousInstallation(dest);
				replacing = false;
			}

			Directory.CreateDirectory(Path.GetDirectoryName(zipCopy));
			Log("Yayından doğrulanmış paket hazırlanıyor…");
			File.Copy(publication.PackagePath, zipCopy, true);
			if (new FileInfo(zipCopy).Length != publication.SizeBytes || Digest(zipCopy) != publication.Sha256)
				throw new InvalidDataException("İndirilen paket manifest SHA-256 değeriyle eşleşmiyor.");
			string prefix = Validate(zipCopy);
			Directory.CreateDirectory(stage);
			string stagePrefix = stage + Path.DirectorySeparatorChar;
			using (var zip = ZipFile.OpenRead(zipCopy))
			{
				foreach (var entry in zip.Entries)
				{
					stop.Token.ThrowIfCancellationRequested();
					var fullName = entry.FullName;
					if (!fullName.StartsWith(prefix, StringComparison.Ordinal)) continue;
					var relative = fullName.Substring(prefix.Length);
					if (relative.Length == 0) continue;
					var fullPath = Path.GetFullPath(Path.Combine(stage, relative.Replace('/', Path.DirectorySeparatorChar)));
					if (!fullPath.StartsWith(stagePrefix, StringComparison.OrdinalIgnoreCase))
						throw new InvalidDataException("ZIP hedefi güvenli klasör dışında.");
					if (fullName.EndsWith("/")) { Directory.CreateDirectory(fullPath); continue; }
					Directory.CreateDirectory(Path.GetDirectoryName(fullPath));
					using (var input = entry.Open())
					using (var output = new FileStream(fullPath, FileMode.CreateNew, FileAccess.Write, FileShare.None))
						input.CopyTo(output);
					lock (this) { transferCount++; currentTransferredName = Path.GetFileName(relative); }
					Log("Aktarıldı: " + Path.GetFileName(relative));
				}
			}

			if (replacing && (File.GetAttributes(dest) & FileAttributes.ReparsePoint) != 0)
				throw new IOException("Kurulum hedefi bağlantılı bir klasör.");

			if (replacing && !cleanInstall)
			{
				foreach (var name in new[] { "csv", "kayitlar", "cache", "local_data", "local_cache", "logs", "quarantine", "data", "data_v2", "veri", "_runtime", "_runtime_packages" })
				{
					var from = Path.Combine(dest, name);
					var to = Path.Combine(stage, name);
					if (Directory.Exists(from)) CopyUserDataTree(from, to, name != "_runtime" && name != "_runtime_packages");
				}
			}

			var brandDir = Path.Combine(stage, "assets", "brand");
			Directory.CreateDirectory(brandDir);
			using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("TalepKontrol.ico"))
			{
				if (stream != null)
				{
					using var output = File.Create(Path.Combine(brandDir, "talep-kontrol.ico"));
					stream.CopyTo(output);
				}
			}

			stop.Token.ThrowIfCancellationRequested();
			// ZIP bitti (ör. windows_launcher.py = son dosya). Swap öncesi kilitleri tekrar çöz.
			StopRunningServices(Log, dest);
			if (!replacing && Directory.Exists(dest))
			{
				TryDeleteDirectory(dest, Log);
			}
			if (Directory.Exists(dest) != replacing)
			{
				throw new IOException(
					"Eski kurulum klasörü kilitli veya kurulum sırasında değişti. " +
					"Talep Kontrol penceresini ve arka plan Python/WebView2 süreçlerini kapatıp yeniden deneyin.");
			}

			Directory.CreateDirectory(Path.GetDirectoryName(dest));
			if (replacing)
			{
				try
				{
					Directory.Move(dest, previous);
					movedOld = true;
				}
				catch (Exception ex)
				{
					StopRunningServices(Log, dest);
					try
					{
						Directory.Move(dest, previous);
						movedOld = true;
					}
					catch
					{
						throw new IOException(
							"Mevcut kurulum taşınamadı (dosya kilidi). Talep Kontrol’u kapatın. Ayrıntı: " + ex.Message, ex);
					}
				}
			}
			try { Directory.Move(stage, dest); }
			catch (Exception ex)
			{
				if (movedOld && !Directory.Exists(dest)) Directory.Move(previous, dest);
				throw new IOException("Yeni paket hedef klasöre alınamadı: " + ex.Message, ex);
			}

			try { WriteReceipt(publication, dest, cleanInstall); }
			catch (Exception ex) { Log("Bilgi: Güncelleme kaydı yazılamadı: " + ex.Message); }
			try { Shortcut(dest); }
			catch (Exception ex) { Log("Kurulum tamamlandı; kısayol oluşturulamadı: " + ex.Message); }

			if (movedOld)
			{
				try { Directory.Delete(previous, true); }
				catch (Exception ex) { Log("Eski geçici klasör silinemedi: " + previous + " | " + ex.Message); }
			}
			Log(cleanInstall ? "Temiz kurulum tamamlandı." : (replacing ? "Uygulama güncellendi." : "Uygulama kuruldu."));
		}
		catch
		{
			if (movedOld && !Directory.Exists(dest) && Directory.Exists(previous)) Directory.Move(previous, dest);
			throw;
		}
		finally
		{
			try { if (File.Exists(zipCopy)) File.Delete(zipCopy); } catch { }
			try { if (Directory.Exists(stage)) Directory.Delete(stage, true); } catch { }
		}
	}

	void CopyUserDataTree(string from, string to, bool overwrite)
	{
		stop.Token.ThrowIfCancellationRequested();
		if ((File.GetAttributes(from) & FileAttributes.ReparsePoint) != 0)
			throw new IOException("Bağlantılı veri klasörü engellendi.");
		Directory.CreateDirectory(to);
		foreach (var file in Directory.GetFiles(from))
		{
			stop.Token.ThrowIfCancellationRequested();
			if ((File.GetAttributes(file) & FileAttributes.ReparsePoint) != 0)
				throw new IOException("Bağlantılı dosya engellendi: " + file);
			var dest = Path.Combine(to, Path.GetFileName(file));
			if (overwrite || !File.Exists(dest)) File.Copy(file, dest, overwrite);
		}
		foreach (var dir in Directory.GetDirectories(from))
			CopyUserDataTree(dir, Path.Combine(to, Path.GetFileName(dir)), overwrite);
	}

	static void WriteReceipt(ActivePublication item, string installDir, bool cleanInstall)
	{
		var dir = Path.Combine(UserDataRoot, "Guncelleme");
		Directory.CreateDirectory(dir);
		var payload =
			"{\"product\":\"Talep Kontrol\",\"sha256\":\"" + item.Sha256 +
			"\",\"release_id\":\"" + item.ReleaseId +
			"\",\"installed_utc\":\"" + DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ") +
			"\",\"install_dir\":\"" + installDir.Replace("\\", "\\\\") +
			"\",\"clean_install\":" + (cleanInstall ? "true" : "false") + "}";
		File.WriteAllText(Path.Combine(dir, "son_kurulum.json"), payload, new UTF8Encoding(false));
	}

	void Shortcut(string dest)
	{
		var launcher = Path.Combine(dest, "Talep Kontrol.vbs");
		if (!File.Exists(launcher)) throw new FileNotFoundException("Otomatik başlatıcı eksik.", launcher);
		dynamic shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
		dynamic sc = shell.CreateShortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Talep Kontrol.lnk"));
		sc.TargetPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "wscript.exe");
		sc.Arguments = "\"" + launcher + "\"";
		sc.WorkingDirectory = dest;
		var ico = Path.Combine(dest, "assets", "brand", "talep-kontrol.ico");
		if (File.Exists(ico)) sc.IconLocation = ico + ",0";
		sc.Description = "Talep Kontrol";
		sc.Save();
	}

	static ActivePublication ReadActivePublication(string shareRoot)
	{
		if (string.IsNullOrWhiteSpace(shareRoot))
			throw new InvalidDataException("Ortak güncelleme yolu belirtilmemiş.");
		var fullPath = Path.GetFullPath(shareRoot.Trim().TrimEnd('\\'));
		var manifestPath = Path.Combine(fullPath, "Aktif", "manifest.json");
		if (!File.Exists(manifestPath))
			throw new FileNotFoundException("Yönetim Panelinden onaylı Aktif yayın bulunamadı.", manifestPath);
		ActivePublication pub;
		using (var fs = File.OpenRead(manifestPath))
			pub = (ActivePublication)new DataContractJsonSerializer(typeof(ActivePublication)).ReadObject(fs);
		if (pub == null || pub.Schema != 1 || pub.Product != "Talep Kontrol")
			throw new InvalidDataException("Aktif manifest türü veya ürün adı geçersiz.");
		if (!Regex.IsMatch(pub.ReleaseId ?? "", @"\A[A-Za-z0-9_-]{1,100}\z"))
			throw new InvalidDataException("Yayın kimliği hatalı.");
		var expected = "Paketler/" + pub.ReleaseId + "/TalepKontrol.zip";
		if (pub.Package != expected)
			throw new InvalidDataException("Aktif manifest paket yolu yayın kimliğiyle eşleşmiyor.");
		if (!Regex.IsMatch(pub.Sha256 ?? "", @"\A[a-f0-9]{64}\z") || pub.SizeBytes <= 0 || pub.SizeBytes > 1073741824)
			throw new InvalidDataException("Aktif manifest bütünlük bilgisi geçersiz.");
		var aktif = Path.Combine(fullPath, "Aktif");
		pub.PackagePath = Path.GetFullPath(Path.Combine(aktif, "Paketler", pub.ReleaseId, "TalepKontrol.zip"));
		var packagesRoot = Path.Combine(aktif, "Paketler");
		if (!pub.PackagePath.StartsWith(packagesRoot + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
			throw new InvalidDataException("Yayın paketi izinli klasör dışında.");
		return pub;
	}

	static string Digest(string file)
	{
		using var sha = SHA256.Create();
		using var fs = File.OpenRead(file);
		return BitConverter.ToString(sha.ComputeHash(fs)).Replace("-", "").ToLowerInvariant();
	}

	static void VerifyApprovedPackage(ActivePublication item)
	{
		if (!File.Exists(item.PackagePath))
			throw new FileNotFoundException("Aktif yayın paketi bulunamadı.", item.PackagePath);
		if (new FileInfo(item.PackagePath).Length != item.SizeBytes || Digest(item.PackagePath) != item.Sha256)
			throw new InvalidDataException("Aktif yayın boyutu veya SHA-256 bütünlüğü uyuşmuyor.");
	}

	static string Validate(string file)
	{
		using var zip = ZipFile.OpenRead(file);
		var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
		long total = 0;
		int count = 0;
		var required = new HashSet<string>(new[]
		{
			"Talep Kontrol.vbs", "AUTO_BASLAT.ps1", "otomatik_guncelleyici.py", "START_GUI.ps1", "server.py", "index.html", "config.json", "windows_launcher.py",
			"PYTHON_BOOTSTRAP.ps1", "WEBVIEW2_HAZIRLA.ps1", "amount-analysis.css", "app.js", "assets/brand/talep-kontrol-kurumsal.png", "assets/brand/talep-kontrol.ico.png",
			"brand-v1.css", "desktop-status.css", "desktop-status.js", "export-utils.js", "form-elements.css", "help-ui.css", "help-ui.js",
			"operations-experience.css", "operations-experience.js", "operations-tables.js", "operations-work.css", "operations-work.js", "responsive.css",
			"startup_runner.py", "styles.css", "ux28j.css", "ux28j.js", "webgl-themes28l.css", "webgl-themes28l.js", "control_read_index.py",
			"data_architecture_v2.py", "f604_summary.py", "form_excel.py", "kesif_drafts28q.py", "project_ids28r.py", "mb51_reconciliation.py",
			"commitment_balances.py", "capacity_projection.py", "capacity_source_facts.py", "operations_aggregation.py", "central_security.py",
			"indexed_engine.py", "parquet_minimal.py", "source_row_diff.py", "central_index_snapshot.py"
		}, StringComparer.OrdinalIgnoreCase);
		ZipArchiveEntry configEntry = null, launcherEntry = null;
		foreach (var entry in zip.Entries)
		{
			var fullName = entry.FullName;
			if (fullName == "Talep Kontrol/") continue;
			if (fullName.Contains("\\") || fullName.IndexOf('\0') >= 0 || !fullName.StartsWith("Talep Kontrol/", StringComparison.Ordinal) ||
				fullName.Contains(":") || fullName.StartsWith("/") || fullName.StartsWith("//"))
				throw new InvalidDataException("Güvensiz veya beklenmeyen ZIP yolu: " + fullName);
			var relative = fullName.Substring("Talep Kontrol/".Length).TrimEnd('/');
			if (string.IsNullOrEmpty(relative)) continue;
			foreach (var part in relative.Split('/'))
			{
				if (string.IsNullOrWhiteSpace(part) || part == "." || part == ".." || part.TrimEnd(' ', '.') != part ||
					part.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
					throw new InvalidDataException("Güvensiz ZIP bileşeni: " + fullName);
			}
			if (!seen.Add(relative)) throw new InvalidDataException("ZIP içinde çakışan dosya adı: " + fullName);
			if (!fullName.EndsWith("/"))
			{
				required.Remove(relative);
				total = checked(total + entry.Length);
				count++;
				if (relative == "config.json") configEntry = entry;
				if (relative == "Talep Kontrol.vbs") launcherEntry = entry;
			}
			if (total > 1000000000 || count > 3000)
				throw new InvalidDataException("Paket açılım güvenlik sınırını aşıyor.");
		}
		if (required.Count != 0)
			throw new InvalidDataException("Otomatik güncelleme için gerekli dosyalar eksik: " + string.Join(", ", required));
		InstalledConfiguration conf;
		using (var stream = configEntry.Open())
			conf = (InstalledConfiguration)new DataContractJsonSerializer(typeof(InstalledConfiguration)).ReadObject(stream);
		if (conf == null || conf.ProductName != "Talep Kontrol" || conf.SharedWritesEnabled ||
			string.IsNullOrEmpty(conf.ExternalRoot) || !conf.ExternalRoot.StartsWith(@"\\") ||
			!conf.AutoInstallUpdates || string.IsNullOrEmpty(conf.UpdateShare) ||
			!conf.UpdateShare.EndsWith(@"\9-Uygulama\Aktif", StringComparison.OrdinalIgnoreCase))
			throw new InvalidDataException("Uygulama otomatik güncelleme için yapılandırılmamış.");
		string launcherText;
		using (var reader = new StreamReader(launcherEntry.Open(), Encoding.UTF8, true))
			launcherText = reader.ReadToEnd();
		if (launcherText.IndexOf("AUTO_BASLAT.ps1", StringComparison.OrdinalIgnoreCase) < 0)
			throw new InvalidDataException("Masaüstü başlatıcısı otomatik güncelleme akışına bağlı değil.");
		return "Talep Kontrol/";
	}
}
