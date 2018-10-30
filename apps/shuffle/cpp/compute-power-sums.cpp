#include <NTL/ZZ_pXFactoring.h>
#include <cassert>
#include <chrono>
#include <fstream>
#include <sys/stat.h>
#include <fcntl.h>


#define LOCK_FILE_NAME "lock.file"


using namespace std;
using namespace NTL;
using namespace std::chrono;


Vec<ZZ_p> computePowers(
        const ZZ_p &a,
        const unsigned int &k,
        const Vec<ZZ_p> &bs,
        bool useAMinusB,
        ZZ_p aMinusB
    )
{
    assert (bs.length() == k);

    aMinusB = useAMinusB ? aMinusB : a - bs[0];
    Vec<ZZ_p> apows;
    apows.SetLength(k+1);
    apows[0] = a;

    Vec<ZZ_p> DiagMinus1;
    DiagMinus1.append(ZZ_p(1));

    for (unsigned int m = 1; m <= k; m++)
    {
        Vec<ZZ_p> DiagM;
        DiagM.SetLength(m+1);
        DiagM[0]  = bs[m-1];
        ZZ_p sum(0);
        for (unsigned int i = 1; i <= m; i++)
        {
            sum += DiagMinus1[i-1];
            DiagM[i] = aMinusB * sum + bs[m-1];
        }

        apows[m] = DiagM[m];
        DiagMinus1 = DiagM;
    }

    // a^index
    apows[0] = 1;
    return apows;
}

inline ZZ readZZ(istream& stream)
{
    string temp;
    getline (stream, temp);
    temp += "\0";
    return conv<ZZ>(temp.c_str());
}

inline ZZ_p readZZ_p(istream& stream)
{
    string temp;
    getline (stream, temp);
    temp += "\0";
    return to_ZZ_p(conv<ZZ>(temp.c_str()));
}

inline int readInt(istream& stream)
{
    string temp;
    getline (stream, temp);
    temp += "\0";
    return atoi(temp.c_str());
}

inline bool doesFileExist(const string& name)
{
  struct stat buffer;
  return (stat (name.c_str(), &buffer) == 0);
}

void writePowersToFile(
        const string& sumFileName,
        Vec<ZZ_p> apows,
        const ZZ& fieldModulus,
        const unsigned int& k
    )
{
    bool isExistingFile = doesFileExist(sumFileName);
    ios_base::openmode mode = (isExistingFile ? ios::in | ios::out : ios::out);

    fstream sumFile(sumFileName, mode);

    // If file exists, read and sum powers.
    if (isExistingFile)
    {
        ZZ modulus_in_file = readZZ(sumFile);
        // cout << "Modulus in file: " << modulus_in_file << endl;
        unsigned int k_in_file = readInt(sumFile);
        // cout << "k: " << k << endl;
        assert (modulus_in_file == fieldModulus);
        assert (k == k_in_file);

        // Sum the powers.
        for (int idx = 1; idx <= k; idx++)
        {
            ZZ_p powerSum = readZZ_p(sumFile);
            // cout << idx << "\t" << powerSum << endl;
            apows[idx] += powerSum;
        }

        // Go to beginning of the file.
        sumFile.clear();
        sumFile.seekg(0, ios::beg);
    }

    sumFile << fieldModulus << endl;
    sumFile << k << endl;

    for (int i = 1; i <= k; i++)
    {
        sumFile << apows[i] << endl;
    }

    // Close the file.
    sumFile.close();
}

/**
 * This method uses a lock file. It takes a lock on the lock file and then
 * writes on the original file. Locking will not work if the original file is
 * modified by some other process which doesn't take a lock on the same lock
 * file.
 * */
void writeUsingLockFile(
        const string& sumFileName,
        Vec<ZZ_p> apows,
        const ZZ& fieldModulus,
        const unsigned int& k
    )
{
    //Declare and set up a flock object from fcntl.
    struct flock outputFileLock;
    outputFileLock.l_type = F_WRLCK; /* Write lock */
    outputFileLock.l_whence = SEEK_SET;
    outputFileLock.l_start = 0;
    outputFileLock.l_len = 0; /* Lock whole file */

    // Open lock file in write mode and request lock.
    FILE* outputFile = fopen(LOCK_FILE_NAME, "w");
    if (outputFile == NULL)
    {
        cout << "Something bad happened\n";
        exit(1);
    }

    // Get file descriptor associated with file handle.
    int fd = fileno(outputFile);

    // Request the lock.  We will wait forever until we get the lock.
    if (fcntl(fd, F_SETLKW, &outputFileLock) == -1)
	{
        cout << "ERROR: could not obtain lock on " << outputFile << '\n';
        exit(1);
	}

    writePowersToFile(sumFileName, apows, fieldModulus, k);

    // Release lock and close file.
    outputFileLock.l_type = F_UNLCK;
    if (fcntl(fd, F_UNLCK, &outputFileLock) == -1)
	{
	    cout << "ERROR: could not release lock on " << outputFile << '\n';
        exit(1);
 	}

    fclose(outputFile);
}

/**
 * Input:
 * fieldModulus: Modulus of the field.
 * a : Number whose powers need to be computed.
 * a-b : Opened value of a - b
 * k : Number of powers to be computed.
 * bs : k Pre computed powers of some random number.
 * */
void runWithInputs(const string& inputFileName, const string& sumFileName)
{
    ifstream inputFile(inputFileName);

    ZZ fieldModulus = readZZ(inputFile);
    // cout << "modulus: " << fieldModulus << endl;

    // Initialize the field with the modulus.
    ZZ_p::init(ZZ(fieldModulus));

    ZZ_p a = readZZ_p(inputFile);
    // cout << "a: " << a << endl;

    ZZ_p aMinusB = readZZ_p(inputFile);
    // cout << "a-b: " << aMinusB << endl;

    // Not doing a cin since the new line is causing issues.
    unsigned int k = readInt(inputFile);
    // cout << "k: " << k << endl;

    Vec<ZZ_p> bs;
    bs.SetLength(k);
    for (int i = 0; i < k; i++)
    {
        bs[i] = readZZ_p(inputFile);
        // cout << "bs[" << i << "] " << bs[i] << endl;
    }

    inputFile.close();

    high_resolution_clock::time_point t1 = high_resolution_clock::now();
    auto apows = computePowers(a, k, bs, true, aMinusB);
    high_resolution_clock::time_point t2 = high_resolution_clock::now();
    // cout << "Powers computed" << endl;

    high_resolution_clock::time_point t3 = high_resolution_clock::now();
    writeUsingLockFile(sumFileName, apows, fieldModulus, k);
    high_resolution_clock::time_point t4 = high_resolution_clock::now();

    cout << "Time taken to compute powers: "
        <<  (float)duration_cast<microseconds>(t2 - t1).count()/1000000
        << " seconds!" << endl;

    cout << "Time taken to write file: "
        <<  (float)duration_cast<microseconds>(t4 - t3).count()/1000000
        << " seconds!" << endl;
}

int main(int argc, char* argv[])
{
    runWithInputs(string(argv[1]), string(argv[2]));
    return 0;
}