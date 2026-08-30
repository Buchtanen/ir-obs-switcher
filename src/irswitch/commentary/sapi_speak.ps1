# Speak via SAPI into memory, then waveOut to one playback device.
# When IRSWITCH_TTS_DEVICE is set, never use the Windows default endpoint.
$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Threading;
public static class IrswitchWaveOut {
  [StructLayout(LayoutKind.Sequential)]
  public struct WAVEFORMATEX {
    public ushort wFormatTag;
    public ushort nChannels;
    public uint nSamplesPerSec;
    public uint nAvgBytesPerSec;
    public ushort nBlockAlign;
    public ushort wBitsPerSample;
    public ushort cbSize;
  }
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
  public struct WAVEOUTCAPS {
    public ushort wMid;
    public ushort wPid;
    public uint vDriverVersion;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
    public string szPname;
    public uint dwFormats;
    public ushort wChannels;
    public ushort wReserved;
    public uint dwSupport;
  }
  [StructLayout(LayoutKind.Sequential)]
  public struct WAVEHDR {
    public IntPtr lpData;
    public uint dwBufferLength;
    public uint dwBytesRecorded;
    public IntPtr dwUser;
    public uint dwFlags;
    public uint dwLoops;
    public IntPtr lpNext;
    public IntPtr reserved;
  }
  [DllImport("winmm.dll")] public static extern int waveOutGetNumDevs();
  [DllImport("winmm.dll", CharSet = CharSet.Auto)]
  public static extern int waveOutGetDevCaps(int uDeviceID, ref WAVEOUTCAPS pwoc, int cbwoc);
  [DllImport("winmm.dll")]
  public static extern int waveOutOpen(out IntPtr phwo, int uDeviceID, ref WAVEFORMATEX pwfx, IntPtr dwCallback, IntPtr dwInstance, int fdwOpen);
  [DllImport("winmm.dll")]
  public static extern int waveOutPrepareHeader(IntPtr hwo, ref WAVEHDR pwh, int cbwh);
  [DllImport("winmm.dll")]
  public static extern int waveOutWrite(IntPtr hwo, ref WAVEHDR pwh, int cbwh);
  [DllImport("winmm.dll")]
  public static extern int waveOutUnprepareHeader(IntPtr hwo, ref WAVEHDR pwh, int cbwh);
  [DllImport("winmm.dll")]
  public static extern int waveOutClose(IntPtr hwo);

  public static int FindDevice(string needle) {
    if (string.IsNullOrWhiteSpace(needle)) return -1;
    string want = needle.ToLowerInvariant();
    int n = waveOutGetNumDevs();
    int fallback = -1;
    for (int i = 0; i < n; i++) {
      var caps = new WAVEOUTCAPS();
      waveOutGetDevCaps(i, ref caps, Marshal.SizeOf(typeof(WAVEOUTCAPS)));
      string low = (caps.szPname ?? "").ToLowerInvariant();
      if (low.IndexOf(want) < 0) continue;
      if (low.Contains("16ch")) {
        if (fallback < 0) fallback = i;
        continue;
      }
      return i;
    }
    return fallback;
  }

  public static string DeviceName(int id) {
    var caps = new WAVEOUTCAPS();
    waveOutGetDevCaps(id, ref caps, Marshal.SizeOf(typeof(WAVEOUTCAPS)));
    return caps.szPname ?? "";
  }

  public static void Play(int deviceId, byte[] pcm, ushort channels, uint rate, ushort bits) {
    if (pcm == null || pcm.Length == 0) throw new Exception("empty pcm");
    var fmt = new WAVEFORMATEX();
    fmt.wFormatTag = 1;
    fmt.nChannels = channels;
    fmt.nSamplesPerSec = rate;
    fmt.wBitsPerSample = bits;
    fmt.nBlockAlign = (ushort)(channels * (bits / 8));
    fmt.nAvgBytesPerSec = rate * fmt.nBlockAlign;
    IntPtr hwo;
    int hr = waveOutOpen(out hwo, deviceId, ref fmt, IntPtr.Zero, IntPtr.Zero, 0);
    if (hr != 0) throw new Exception("waveOutOpen hr=" + hr + " device=" + deviceId);
    IntPtr buf = Marshal.AllocHGlobal(pcm.Length);
    try {
      Marshal.Copy(pcm, 0, buf, pcm.Length);
      var hdr = new WAVEHDR();
      hdr.lpData = buf;
      hdr.dwBufferLength = (uint)pcm.Length;
      int hsz = Marshal.SizeOf(typeof(WAVEHDR));
      hr = waveOutPrepareHeader(hwo, ref hdr, hsz);
      if (hr != 0) throw new Exception("waveOutPrepareHeader hr=" + hr);
      hr = waveOutWrite(hwo, ref hdr, hsz);
      if (hr != 0) throw new Exception("waveOutWrite hr=" + hr);
      int waitMs = (int)((pcm.Length * 1000.0 / Math.Max(1, fmt.nAvgBytesPerSec)) + 80);
      Thread.Sleep(Math.Max(waitMs, 50));
      waveOutUnprepareHeader(hwo, ref hdr, hsz);
    } finally {
      waveOutClose(hwo);
      Marshal.FreeHGlobal(buf);
    }
  }
}
"@

$voice = New-Object -ComObject SAPI.SpVoice
$rate = 0
[void][int]::TryParse($env:IRSWITCH_TTS_RATE, [ref]$rate)
if ($rate -lt -10) { $rate = -10 }
if ($rate -gt 10) { $rate = 10 }
$voice.Rate = $rate
if ($env:IRSWITCH_TTS_VOICE) {
  $wantVoice = $env:IRSWITCH_TTS_VOICE
  $voices = $voice.GetVoices()
  for ($i = 0; $i -lt $voices.Count; $i++) {
    $desc = $voices.Item($i).GetDescription()
    if ($desc -eq $wantVoice -or $desc.Contains($wantVoice)) {
      $voice.Voice = $voices.Item($i)
      break
    }
  }
}

$text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($env:IRSWITCH_TTS_B64))
$wantDev = $env:IRSWITCH_TTS_DEVICE
if (-not $wantDev) {
  $voice.Speak($text, 0)
  Write-Output "tts_device=default"
  exit 0
}

$devId = [IrswitchWaveOut]::FindDevice($wantDev)
if ($devId -lt 0) {
  Write-Error "tts device not found: $wantDev"
  exit 1
}

$stream = New-Object -ComObject SAPI.SpMemoryStream
$voice.AllowAudioOutputFormatChangesOnNextSet = $true
$voice.AudioOutputStream = $stream
$voice.Speak($text, 0)
$stream.Seek(0) | Out-Null
$pcm = [byte[]]$stream.GetData()
if (-not $pcm -or $pcm.Length -lt 16) {
  Write-Error "tts produced no pcm"
  exit 1
}
$wfx = $stream.Format.GetWaveFormatEx()
$ch = [uint16]$wfx.Channels
$rateHz = [uint32]$wfx.SamplesPerSec
$bits = [uint16]$wfx.BitsPerSample
if ($ch -lt 1) { $ch = 1 }
if ($rateHz -lt 8000) { $rateHz = 22050 }
if ($bits -lt 8) { $bits = 16 }
[IrswitchWaveOut]::Play($devId, $pcm, $ch, $rateHz, $bits)
Write-Output ("tts_device=" + [IrswitchWaveOut]::DeviceName($devId) + " wave=" + $devId)
