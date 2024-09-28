# Set these values:
$stashProtocol = "http"
$stashHost = "localhost:9999"
$sessionCookie = "YOUR_SESSION_COOKIE_HERE"


# Do not modify the rest of the script
$graphqlEndpoint = "${stashProtocol}://${stashHost}/graphql"
$referer = "${stashProtocol}://${stashHost}/"

# Create a web session
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$session.Cookies.Add((New-Object System.Net.Cookie("session", $sessionCookie, "/", $stashHost)))

# Define the GraphQL query
$graphqlQuery = @'
query FindPerformers($filter: FindFilterType, $performer_filter: PerformerFilterType, $performer_ids: [Int!]) {
  findPerformers(
    filter: $filter
    performer_filter: $performer_filter
    performer_ids: $performer_ids
  ) {
    count
    performers {
      id
      name
      image_path
      stash_ids {
        stash_id
        endpoint
      }
    }
  }
}
'@

# Define the variables
$variables = @{
    filter = @{
        q = ""
        page = 1
        per_page = 250
        sort = "name"
        direction = "ASC"
    }
    performer_filter = @{
        filter_favorites = $true
    }
    performer_ids = $null
}

# Create the GraphQL request body
$requestBody = @{
    query = $graphqlQuery
    variables = $variables
} | ConvertTo-Json

# Set headers for the GraphQL request
$headers = @{
    "Content-Type" = "application/json"
}

# Send the GraphQL request
$response = Invoke-RestMethod -Uri $graphqlEndpoint -Method Post -Headers $headers -Body $requestBody -WebSession $session

# Check if the response contains performers
if ($response.data.findPerformers.performers) {
    $performers = $response.data.findPerformers.performers

    # Iterate over each performer
    foreach ($performer in $performers) {
        $name = $performer.name
        $id = $performer.id
        $imagePath = $performer.image_path

        # Find the stash_id from stash_ids where the endpoint matches https://stashdb.org/graphql
        $stashId = $null
        foreach ($stash in $performer.stash_ids) {
            if ($stash.endpoint -eq "https://stashdb.org/graphql") {
                $stashId = $stash.stash_id
                break
            }
        }

        # Skip if no stashId or image_path is available
        if (-not $stashId -or -not $imagePath) {
            Write-Host "Skipping performer: $name (ID: $id) - No stash_id or image_path"
            continue
        }

        # Define the filename in the format "<performer name> [<stash_id>].jpg"
        $filename = "$name [$stashId].jpg"

        # Define the output file path using the current directory
        $outputPath = Join-Path -Path $PWD.Path -ChildPath $filename

        # Download the image file
        try {
            $imageHeaders = @{
                "authority" = $stashHost
                "method" = "GET"
                "scheme" = "https"
                "accept" = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
                "accept-encoding" = "gzip, deflate, br, zstd"
                "accept-language" = "en-US,en;q=0.9,fi;q=0.8"
                "cache-control" = "no-cache"
                "pragma" = "no-cache"
                "upgrade-insecure-requests" = "1"
            }

            Invoke-WebRequest -UseBasicParsing -Uri $imagePath -WebSession $session -Headers $imageHeaders -OutFile $outputPath
            Write-Host "Downloaded: $filename"
        } catch {
            Write-Host "Failed to download image for performer: $name (ID: $id)"
            Write-Host $_.Exception.Message
        }
    }
} else {
    Write-Host "No performers found."
}
