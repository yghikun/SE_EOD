$Mode = [string]$args[0]
$ArchivePath = [string]$args[1]
$EntryName = [string]$args[2]

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
try {
    if ($Mode -eq '-Z1') {
        foreach ($entry in $archive.Entries) {
            [Console]::Out.WriteLine($entry.FullName)
        }
        exit 0
    }
    if ($Mode -eq '-p') {
        $entry = $archive.GetEntry($EntryName)
        if ($null -eq $entry) { exit 11 }
        $input = $entry.Open()
        try {
            $output = [Console]::OpenStandardOutput()
            $input.CopyTo($output)
            $output.Flush()
        } finally {
            $input.Dispose()
        }
        exit 0
    }
    exit 2
} finally {
    $archive.Dispose()
}
