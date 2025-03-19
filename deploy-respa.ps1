Push-Location -Path /Users/terho.craven/Repos/Turku/gofore-respa
./AzureUtil.ps1 deploy
./AzureUtil.ps1 dbimport /Users/terho.craven/CopyFiles/Turku/respa/103respa-test.sql
./AzureUtil.ps1 copyfiles apifiles /Users/terho.craven/CopyFiles/Turku/respa/media
./AzureUtil.ps1 copyfiles apifiles /Users/terho.craven/CopyFiles/Turku/respa/static
./AzureUtil.ps1 copyfiles apifiles /Users/terho.craven/CopyFiles/Turku/respa/static_src
./AzureUtil.ps1 build api /Users/terho.craven/Repos/Turku/gofore-respa
./AzureUtil.ps1 build ui /Users/terho.craven/Repos/Turku/gofore-varaamo
Pop-Location