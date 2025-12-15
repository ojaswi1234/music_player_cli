
Add-Type -AssemblyName presentationCore

$global:mediaPlayer = $null
$global:isPaused = $false

function Play-Audio {
    param([string]$url)
    
    try {
        Write-Host "DEBUG: Starting playback for URL: $url"
        
        # Create new media player
        $global:mediaPlayer = New-Object System.Windows.Media.MediaPlayer
        
        # Set volume to max
        $global:mediaPlayer.Volume = 1.0
        
        Write-Host "DEBUG: MediaPlayer created, opening URL..."
        $global:mediaPlayer.Open([uri]$url)
        
        # Wait for media to open
        Start-Sleep -Seconds 2
        
        Write-Host "DEBUG: Starting playback..."
        $global:mediaPlayer.Play()
        $global:isPaused = $false
        
        Write-Host "PLAYING"
        Write-Host "DEBUG: Volume is set to $($global:mediaPlayer.Volume)"
        
        # Keep checking if playback has ended
        $timeout = 0
        while ($true) {
            Start-Sleep -Milliseconds 500
            $timeout++
            
            if ($timeout % 10 -eq 0) {
                Write-Host "DEBUG: Still playing... Position: $($global:mediaPlayer.Position.TotalSeconds)s"
            }
            
            if ($global:mediaPlayer.NaturalDuration.HasTimeSpan) {
                $position = $global:mediaPlayer.Position.TotalSeconds
                $duration = $global:mediaPlayer.NaturalDuration.TimeSpan.TotalSeconds
                
                Write-Host "DEBUG: Position: $position / Duration: $duration"
                
                if ($position -ge ($duration - 1) -and $duration -gt 0) {
                    Write-Host "ENDED"
                    break
                }
            }
            
            # Timeout after 30 minutes
            if ($timeout -gt 3600) {
                Write-Host "DEBUG: Timeout reached"
                break
            }
        }
    }
    catch {
        Write-Host "ERROR: $_"
        Write-Host "DEBUG: Exception details: $($_.Exception.Message)"
    }
}

function Pause-Audio {
    if ($global:mediaPlayer -ne $null -and -not $global:isPaused) {
        $global:mediaPlayer.Pause()
        $global:isPaused = $true
        Write-Host "PAUSED"
    }
}

function Resume-Audio {
    if ($global:mediaPlayer -ne $null -and $global:isPaused) {
        $global:mediaPlayer.Play()
        $global:isPaused = $false
        Write-Host "RESUMED"
    }
}

function Stop-Audio {
    if ($global:mediaPlayer -ne $null) {
        $global:mediaPlayer.Stop()
        $global:mediaPlayer.Close()
        $global:mediaPlayer = $null
        $global:isPaused = $false
        Write-Host "STOPPED"
    }
}

function Get-Volume {
    if ($global:mediaPlayer -ne $null) {
        Write-Host "VOLUME:$($global:mediaPlayer.Volume)"
    }
}

# Main command loop
Write-Host "DEBUG: PowerShell audio player started"
while ($true) {
    $command = Read-Host
    Write-Host "DEBUG: Received command: $command"
    
    if ($command -match "^PLAY:(.+)$") {
        $url = $Matches[1]
        Stop-Audio
        Play-Audio -url $url
    }
    elseif ($command -eq "PAUSE") {
        Pause-Audio
    }
    elseif ($command -eq "RESUME") {
        Resume-Audio
    }
    elseif ($command -eq "STOP") {
        Stop-Audio
    }
    elseif ($command -eq "EXIT") {
        Stop-Audio
        break
    }
    elseif ($command -eq "VOLUME") {
        Get-Volume
    }
    elseif ($command -eq "STATUS") {
        if ($global:isPaused) {
            Write-Host "PAUSED"
        }
        elseif ($global:mediaPlayer -ne $null) {
            Write-Host "PLAYING"
        }
        else {
            Write-Host "STOPPED"
        }
    }
}
