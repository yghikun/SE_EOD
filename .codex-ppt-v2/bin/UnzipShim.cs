using System;
using System.IO;
using System.IO.Compression;

public static class UnzipShim
{
    public static int Main(string[] args)
    {
        if (args.Length < 2) return 2;
        using (var archive = ZipFile.OpenRead(args[1]))
        {
            if (args[0] == "-Z1")
            {
                foreach (var entry in archive.Entries)
                    Console.Out.WriteLine(entry.FullName);
                return 0;
            }
            if (args[0] == "-p" && args.Length >= 3)
            {
                var entry = archive.GetEntry(args[2]);
                if (entry == null) return 11;
                using (var input = entry.Open())
                using (var output = Console.OpenStandardOutput())
                    input.CopyTo(output);
                return 0;
            }
        }
        return 2;
    }
}
